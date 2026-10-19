"""Duplicate detection and safe removal (RF-16 to RF-20, ADR 0006, ADR 0009).

1. Scan: hash every photo (SHA-256 + dHash), reusing the cache.
2. Group: exact duplicates (same SHA-256) and near duplicates (dHash within
   ``max_distance``). A near group absorbs the exact copies of its members, so each
   photo belongs to at most one group that is applied.
3. Choose the copy to keep (RF-18): highest resolution > oldest EXIF date > largest
   file > shortest path. The user can override it.
4. Act: move the other copies to ``<folder>/_duplicados/`` with the organizer (manifest
   + undo), or send them to the system trash with explicit confirmation. Before acting,
   every group is checked to keep at least one intact copy (RF-19).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path, PurePosixPath
from types import TracebackType

from face_sorter.config import DUPLICATES_FOLDER, OutputMode, Settings
from face_sorter.core.cache import FaceCache
from face_sorter.core.hashing import ImageHashes, compute_hashes, connected_groups, near_pairs
from face_sorter.core.image_io import sha256_file
from face_sorter.core.scanner import scan
from face_sorter.formatting import human_size
from face_sorter.services.pipeline import ScanCancelled, cache_fingerprint
from face_sorter.services.plan import OrganizationPlan, PlanItem

log = logging.getLogger(__name__)


class DedupeError(Exception):
    """Acting on the duplicates would be unsafe; nothing was changed."""


class DupKind(StrEnum):
    """Kind of duplicate group."""

    EXACT = "exact"
    NEAR = "near"


@dataclass(frozen=True)
class Photo:
    """A photo and the data used to compare copies."""

    path: Path
    size: int
    hashes: ImageHashes

    @property
    def pixels(self) -> int:
        """Resolution in pixels (0 if unknown)."""
        return (self.hashes.width or 0) * (self.hashes.height or 0)


def keep_key(photo: Photo) -> tuple[int, str, int, int, str]:
    """Sort key: the best copy to keep sorts first (RF-18).

    Highest resolution > oldest EXIF date (photos without a date go last) > largest
    file > shortest path. The date comes before the size so that a heavier conversion
    (e.g. JPEG -> PNG, which loses the EXIF date) does not win over the original.
    """
    return (
        -photo.pixels,
        photo.hashes.taken_at or "9999",
        -photo.size,
        len(str(photo.path)),
        str(photo.path).lower(),
    )


@dataclass
class DuplicateGroup:
    """A set of copies of the same photo. ``keep`` stays; the rest are duplicates."""

    id: str
    kind: DupKind
    photos: list[Photo]
    keep: Photo
    distance: int = 0  # largest dHash distance between linked members (0 for exact)

    @property
    def duplicates(self) -> list[Photo]:
        """The copies that would be removed."""
        return [p for p in self.photos if p.path != self.keep.path]

    def set_keep(self, path: Path) -> None:
        """Choose another copy to keep (user override)."""
        for p in self.photos:
            if p.path == Path(path):
                self.keep = p
                return
        raise DedupeError(f"{path} no pertenece al grupo {self.id}")


@dataclass
class DedupeResult:
    """Duplicate groups found under ``root``."""

    root: Path
    groups: list[DuplicateGroup]
    errors: list[tuple[Path, str]] = field(default_factory=list)
    n_photos: int = 0

    def group(self, group_id: str) -> DuplicateGroup:
        """Group by id."""
        for g in self.groups:
            if g.id == group_id:
                return g
        raise KeyError(group_id)

    def default_selection(self, include_near: bool = False) -> list[str]:
        """Ids applied by default: exact groups, plus near ones if ``include_near``."""
        return [g.id for g in self.groups if g.kind is DupKind.EXACT or include_near]

    def summary(self, selected: Iterable[str] | None = None) -> str:
        """Human-readable list of groups (``*`` marks the ones that would be applied)."""
        chosen = set(selected if selected is not None else self.default_selection())
        exact = [g for g in self.groups if g.kind is DupKind.EXACT]
        near = [g for g in self.groups if g.kind is DupKind.NEAR]
        lines = [
            f"Carpeta: {self.root}",
            f"Fotos: {self.n_photos} | grupos exactos: {len(exact)} | "
            f"grupos casi duplicados: {len(near)} | ilegibles: {len(self.errors)}",
        ]
        for g in self.groups:
            mark = "*" if g.id in effective_selection(self, chosen) else " "
            extra = f", distancia <= {g.distance}" if g.kind is DupKind.NEAR else ""
            lines.append(f"{mark} [{g.id}] {len(g.photos)} copias{extra}")
            lines.append(f"    conservar: {self._describe(g.keep)}")
            lines += [f"    retirar:   {self._describe(p)}" for p in g.duplicates]
        if near and not any(g.id in chosen for g in near):
            lines.append("\nLos casi duplicados solo se listan. Usa --near para incluirlos.")
        return "\n".join(lines)

    def _describe(self, p: Photo) -> str:
        rel = p.path.relative_to(self.root) if p.path.is_relative_to(self.root) else p.path
        res = f"{p.hashes.width}x{p.hashes.height}" if p.pixels else "?"
        date = f", {p.hashes.taken_at}" if p.hashes.taken_at else ""
        return f"{rel}  ({res}, {human_size(p.size)}{date})"


ProgressCallback = Callable[[int, int], None]
CancelCheck = Callable[[], bool]


class DedupeScanner:
    """Finds duplicate groups. Use as a context manager so the cache gets closed."""

    def __init__(self, settings: Settings | None = None, cache: FaceCache | None = None) -> None:
        self.settings = settings or Settings()
        self._owns_cache = cache is None
        self.cache = cache or FaceCache(self.settings.cache_path, cache_fingerprint(self.settings))

    def close(self) -> None:
        """Close the cache if this scanner opened it."""
        if self._owns_cache:
            self.cache.close()

    def __enter__(self) -> DedupeScanner:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def hashes(self, path: Path) -> ImageHashes:
        """Hashes of ``path`` (cached when the file did not change)."""
        cached = self.cache.lookup_hashes(path)
        if cached is not None:
            return cached
        hashes = compute_hashes(Path(path).read_bytes())
        self.cache.store_hashes(path, hashes)
        return hashes

    def run(
        self,
        root: Path,
        *,
        exclude: Iterable[Path] = (),
        progress: ProgressCallback | None = None,
        cancel: CancelCheck | None = None,
    ) -> DedupeResult:
        """Hash every photo under ``root`` and group the duplicates.

        Raises:
            ScanCancelled: if ``cancel()`` returns True (hashes so far stay cached).
        """
        root = Path(root).resolve()
        paths = list(scan(root, exclude=exclude))
        photos: list[Photo] = []
        errors: list[tuple[Path, str]] = []
        for done, path in enumerate(paths, start=1):
            if cancel is not None and cancel():
                raise ScanCancelled(f"Cancelled after {done - 1} of {len(paths)} photos")
            try:
                photos.append(Photo(path, path.stat().st_size, self.hashes(path)))
            except OSError as exc:
                log.warning("Cannot read %s: %s", path, exc)
                errors.append((path, str(exc)))
            if progress is not None:
                progress(done, len(paths))
        groups = find_groups(
            photos, self.settings.dedupe.max_distance, self.settings.dedupe.full_compare_limit
        )
        return DedupeResult(root, groups, errors, len(paths))


def find_groups(
    photos: list[Photo], max_distance: int, full_compare_limit: int = 4000
) -> list[DuplicateGroup]:
    """Exact groups (same SHA-256) and near groups (dHash), exact first."""
    by_sha: dict[str, list[Photo]] = {}
    for p in photos:
        by_sha.setdefault(p.hashes.sha256, []).append(p)

    groups: list[DuplicateGroup] = []
    for members in by_sha.values():
        if len(members) > 1:
            ordered = sorted(members, key=keep_key)
            groups.append(
                DuplicateGroup(f"exact-{len(groups) + 1:03d}", DupKind.EXACT, ordered, ordered[0])
            )

    # One representative per distinct content; near groups link representatives and then
    # absorb all their exact copies.
    reps = [min(m, key=keep_key) for m in by_sha.values() if m[0].hashes.phash is not None]
    pairs = near_pairs(
        [r.hashes.phash for r in reps if r.hashes.phash is not None],
        max_distance,
        full_compare_limit=full_compare_limit,
    )
    distance: dict[int, int] = {}
    for i, j, d in pairs:
        distance[i] = max(distance.get(i, 0), d)
        distance[j] = max(distance.get(j, 0), d)
    n_near = 0
    for component in connected_groups(len(reps), pairs):
        members = [p for i in component for p in by_sha[reps[i].hashes.sha256]]
        ordered = sorted(members, key=keep_key)
        n_near += 1
        groups.append(
            DuplicateGroup(
                f"near-{n_near:03d}",
                DupKind.NEAR,
                ordered,
                ordered[0],
                max(distance[i] for i in component),
            )
        )
    return groups


def effective_selection(result: DedupeResult, selected: Iterable[str]) -> list[str]:
    """Selected ids, dropping exact groups absorbed by a selected near group."""
    chosen = set(selected)
    near_paths = {
        p.path for g in result.groups if g.id in chosen and g.kind is DupKind.NEAR for p in g.photos
    }
    return [
        g.id
        for g in result.groups
        if g.id in chosen and not (g.kind is DupKind.EXACT and g.keep.path in near_paths)
    ]


def verify_selection(result: DedupeResult, selected: Iterable[str]) -> list[DuplicateGroup]:
    """Check RF-19 for the groups to apply and return them.

    Every group must keep a copy that still exists, is unchanged since the scan, and is
    not removed by any other group.

    Raises:
        DedupeError: if the invariant does not hold (nothing is changed).
    """
    groups = [result.group(gid) for gid in effective_selection(result, selected)]
    removed = {p.path for g in groups for p in g.duplicates}
    for g in groups:
        keep = g.keep
        if keep.path in removed:
            raise DedupeError(f"[{g.id}] la copia a conservar también se retiraría: {keep.path}")
        if not keep.path.is_file():
            raise DedupeError(f"[{g.id}] la copia a conservar ya no existe: {keep.path}")
        if sha256_file(keep.path) != keep.hashes.sha256:
            raise DedupeError(f"[{g.id}] la copia a conservar cambió desde el escaneo: {keep.path}")
        if not g.duplicates:
            raise DedupeError(f"[{g.id}] no tiene nada que retirar")
    return groups


def build_dedupe_plan(result: DedupeResult, selected: Iterable[str]) -> OrganizationPlan:
    """Plan to move the duplicates of the selected groups to ``<root>/_duplicados/``.

    Each duplicate keeps its path relative to the analysed folder.
    """
    groups = verify_selection(result, selected)
    items = [
        PlanItem(p.path, PurePosixPath(*p.path.relative_to(result.root).parts), g.id)
        for g in groups
        for p in g.duplicates
    ]
    return OrganizationPlan(
        result.root, result.root / DUPLICATES_FOLDER, OutputMode.MOVE, [], items, [], []
    )


@dataclass
class TrashReport:
    """Files sent to the system trash."""

    trashed: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)
    record: Path | None = None

    def summary(self) -> str:
        """Human-readable summary."""
        lines = [f"Enviadas a la papelera: {len(self.trashed)} | fallidas: {len(self.failed)}"]
        lines += [f"  FALLÓ {p}: {e}" for p, e in self.failed]
        lines.append("Se pueden recuperar desde la papelera del sistema.")
        if self.record:
            lines.append(f"Registro: {self.record}")
        return "\n".join(lines)


def trash_duplicates(
    result: DedupeResult,
    selected: Iterable[str],
    *,
    confirm: bool = False,
    send: Callable[[str], None] | None = None,
) -> TrashReport:
    """Send the duplicates of the selected groups to the system trash.

    Never deletes permanently. Requires ``confirm=True``. Checks RF-19 first and
    re-checks each file's content just before trashing it. Writes a JSON record in
    ``<root>/_duplicados/``.

    Raises:
        DedupeError: without confirmation, or if the invariant does not hold.
    """
    if not confirm:
        raise DedupeError("Enviar a la papelera requiere confirmación explícita")
    if send is None:
        from send2trash import send2trash

        send = send2trash
    groups = verify_selection(result, selected)
    report = TrashReport()
    for g in groups:
        for p in g.duplicates:
            try:
                if sha256_file(p.path) != p.hashes.sha256:
                    raise DedupeError("cambió desde el escaneo; no se envió a la papelera")
                send(str(p.path))
                report.trashed.append(str(p.path))
            except (OSError, DedupeError) as exc:
                report.failed.append((str(p.path), str(exc)))
    folder = result.root / DUPLICATES_FOLDER
    folder.mkdir(exist_ok=True)
    report.record = folder / f"trash_{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    report.record.write_text(
        json.dumps(
            {"root": str(result.root), "trashed": report.trashed, "failed": report.failed},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return report

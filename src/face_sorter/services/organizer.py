"""Apply an organization plan safely, with a manifest and undo (RF-10, RF-12, ADR 0003, ADR 0007).

Safety rules:
- Never overwrite: destination files are created exclusively. If a destination already
  exists with identical content it is skipped; otherwise the next free name is used.
- Every copy is verified with SHA-256 before it counts as done.
- Moving requires explicit confirmation. A source is removed only after all its copies
  were verified, and the manifest records the intent beforehand, so undo can always
  restore it.
- The manifest is saved during the run, so even an interrupted run can be undone.
- Undo only deletes files this tool created and that are unchanged since.
"""

from __future__ import annotations

import errno
import json
import logging
import os
import shutil
from collections.abc import Callable, Iterator
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from face_sorter import __version__
from face_sorter.config import (
    COPY_CHUNK_SIZE,
    MANIFEST_PREFIX,
    MANIFEST_SAVE_EVERY,
    OutputMode,
)
from face_sorter.core.image_io import sha256_file
from face_sorter.services.plan import OrganizationPlan, PlanItem

log = logging.getLogger(__name__)

MANIFEST_FORMAT_VERSION = 1
_MAX_NAME_ATTEMPTS = 10_000


class OrganizerError(Exception):
    """The plan cannot be applied (nothing was changed when raised before starting)."""


class EntryResult(StrEnum):
    """Outcome of one planned file placement."""

    CREATED = "created"
    SKIPPED_IDENTICAL = "skipped_identical"
    FAILED = "failed"


class Method(StrEnum):
    """How a destination file was created."""

    COPY = "copy"
    LINK = "link"


class RunStatus(StrEnum):
    """State of an apply run, as stored in the manifest."""

    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    UNDONE = "undone"


class RemovalState(StrEnum):
    """State of a source file in move mode."""

    PENDING = "pending"  # all copies verified; about to be removed
    DONE = "done"
    KEPT = "kept"  # not removed (a copy failed or the run was cancelled)


@dataclass
class ManifestEntry:
    """One file placement."""

    source: str
    dest: str
    group: str
    result: EntryResult
    method: Method | None = None
    sha256: str | None = None
    size: int | None = None
    error: str | None = None


@dataclass
class SourceRemoval:
    """A source file removed (or to be removed) in move mode."""

    source: str
    sha256: str
    state: RemovalState


@dataclass
class Manifest:
    """Record of everything an apply run did. Saved as JSON in the output folder."""

    mode: OutputMode
    source_root: str
    output_root: str
    status: RunStatus = RunStatus.IN_PROGRESS
    entries: list[ManifestEntry] = field(default_factory=list)
    removals: list[SourceRemoval] = field(default_factory=list)
    created_dirs: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: _now())
    finished_at: str | None = None
    app_version: str = __version__
    format_version: int = MANIFEST_FORMAT_VERSION

    def to_dict(self) -> dict[str, Any]:
        """JSON-serializable representation."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Manifest:
        """Rebuild a manifest from :meth:`to_dict` output."""
        if data.get("format_version") != MANIFEST_FORMAT_VERSION:
            raise OrganizerError(f"Unsupported manifest version: {data.get('format_version')}")
        return cls(
            mode=OutputMode(data["mode"]),
            source_root=data["source_root"],
            output_root=data["output_root"],
            status=RunStatus(data["status"]),
            entries=[
                ManifestEntry(
                    **{
                        **e,
                        "result": EntryResult(e["result"]),
                        "method": Method(e["method"]) if e.get("method") else None,
                    }
                )
                for e in data["entries"]
            ],
            removals=[
                SourceRemoval(r["source"], r["sha256"], RemovalState(r["state"]))
                for r in data["removals"]
            ],
            created_dirs=list(data["created_dirs"]),
            created_at=data["created_at"],
            finished_at=data.get("finished_at"),
            app_version=data.get("app_version", "?"),
        )

    def save(self, path: Path) -> None:
        """Write atomically (temp file + replace) so a crash never leaves a broken manifest."""
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)

    @classmethod
    def load(cls, path: Path) -> Manifest:
        """Read a manifest file."""
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise OrganizerError(f"Cannot read manifest {path}: {exc}") from exc
        return cls.from_dict(data)


@dataclass(frozen=True)
class ApplyResult:
    """Summary of an apply run."""

    manifest_path: Path
    manifest: Manifest

    def count(self, result: EntryResult) -> int:
        """Number of entries with ``result``."""
        return sum(1 for e in self.manifest.entries if e.result is result)

    @property
    def fallbacks(self) -> int:
        """Hardlinks that had to be copies (e.g. output on another drive)."""
        if self.manifest.mode is not OutputMode.HARDLINK:
            return 0
        return sum(1 for e in self.manifest.entries if e.method is Method.COPY)

    def summary(self) -> str:
        """Human-readable summary."""
        m = self.manifest
        lines = [
            f"Status: {m.status.value}  (mode: {m.mode.value})",
            f"Created: {self.count(EntryResult.CREATED)} | "
            f"already there (identical): {self.count(EntryResult.SKIPPED_IDENTICAL)} | "
            f"failed: {self.count(EntryResult.FAILED)}",
        ]
        if self.fallbacks:
            lines.append(
                f"Note: {self.fallbacks} hardlink(s) were not possible (different drive or "
                "file system) and were copied instead."
            )
        if m.mode is OutputMode.MOVE:
            done = sum(1 for r in m.removals if r.state is RemovalState.DONE)
            kept = sum(1 for r in m.removals if r.state is RemovalState.KEPT)
            lines.append(f"Originals moved: {done} | kept in place: {kept}")
        for e in m.entries:
            if e.result is EntryResult.FAILED:
                lines.append(f"  FAILED {e.source} -> {e.dest}: {e.error}")
        lines.append(f"Manifest: {self.manifest_path}")
        return "\n".join(lines)


ProgressCallback = Callable[[int, int], None]
CancelCheck = Callable[[], bool]


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _candidates(first: Path) -> Iterator[Path]:
    """``first`` and then ``stem (2).ext``, ``stem (3).ext``... (bounded)."""
    yield first
    for n in range(2, _MAX_NAME_ATTEMPTS):
        yield first.with_name(f"{first.stem} ({n}){first.suffix}")


def _copy_exclusive(src: Path, dst: Path, expected_sha: str) -> None:
    """Copy ``src`` to a *new* file ``dst`` and verify its SHA-256.

    Raises FileExistsError if ``dst`` exists (nothing is touched). On any other failure
    the partial ``dst`` (which this function created) is removed.
    """
    with src.open("rb") as fin, dst.open("xb") as fout:
        try:
            shutil.copyfileobj(fin, fout, COPY_CHUNK_SIZE)
        except BaseException:
            fout.close()
            dst.unlink(missing_ok=True)
            raise
    try:
        shutil.copystat(src, dst)
        actual = sha256_file(dst)
    except BaseException:
        dst.unlink(missing_ok=True)
        raise
    if actual != expected_sha:
        dst.unlink(missing_ok=True)
        raise OrganizerError(f"Verification failed for {dst} (source changed while copying?)")


def _is_link_unsupported(exc: OSError) -> bool:
    """True if ``os.link`` failed because links are impossible here (not a real error)."""
    winerror = getattr(exc, "winerror", None)
    # 17: ERROR_NOT_SAME_DEVICE, 1: ERROR_INVALID_FUNCTION (FAT/exFAT), 50: not supported.
    return exc.errno in (errno.EXDEV, errno.EPERM, errno.ENOTSUP, errno.EMLINK) or winerror in (
        1,
        17,
        50,
    )


class Organizer:
    """Applies one plan. Use :func:`apply_plan` unless you need finer control."""

    def __init__(self, plan: OrganizationPlan) -> None:
        self.plan = plan
        self.output = Path(plan.output_root).resolve()
        self.source_root = Path(plan.source_root).resolve()
        self._sha: dict[Path, str] = {}

    # -- checks ----------------------------------------------------------------------

    def preflight(self) -> None:
        """Validate the plan before touching anything.

        Raises:
            OrganizerError: if the output folder equals the source folder, a destination
                escapes the output folder, or there is not enough free space to copy.
        """
        if self.output == self.source_root:
            raise OrganizerError("The output folder must be different from the source folder")
        for item in self.plan.items:
            dest = (self.output / item.dest).resolve()
            if not _is_within(dest, self.output) or dest == self.output:
                raise OrganizerError(f"Destination outside the output folder: {item.dest}")
        if self.plan.mode is OutputMode.COPY:
            needed = sum(
                item.source.stat().st_size for item in self.plan.items if item.source.is_file()
            )
            probe = self.output
            while not probe.exists() and probe != probe.parent:
                probe = probe.parent
            free = shutil.disk_usage(probe).free
            if needed > free:
                raise OrganizerError(
                    f"Not enough free space in {probe}: need {needed:,} bytes, have {free:,}"
                )

    # -- helpers ---------------------------------------------------------------------

    def _source_sha(self, path: Path) -> str:
        if path not in self._sha:
            self._sha[path] = sha256_file(path)
        return self._sha[path]

    def _ensure_dir(self, directory: Path, manifest: Manifest) -> None:
        missing: list[Path] = []
        probe = directory
        while not probe.exists():
            missing.append(probe)
            probe = probe.parent
        directory.mkdir(parents=True, exist_ok=True)
        manifest.created_dirs += [str(d) for d in reversed(missing)]

    def _place(self, item: PlanItem, manifest: Manifest) -> ManifestEntry:
        src = Path(item.source)
        first = self.output / item.dest
        entry = ManifestEntry(str(src), str(first), item.group, EntryResult.FAILED)
        try:
            if not src.is_file():
                raise OrganizerError("source file not found")
            self._ensure_dir(first.parent, manifest)
            sha = self._source_sha(src)
            entry.sha256, entry.size = sha, src.stat().st_size
            want_link = self.plan.mode in (OutputMode.HARDLINK, OutputMode.MOVE)
            for candidate in _candidates(first):
                try:
                    if want_link:
                        try:
                            os.link(src, candidate)
                            entry.method = Method.LINK
                        except FileExistsError:
                            raise
                        except OSError as exc:
                            if not _is_link_unsupported(exc):
                                raise
                            want_link = False  # e.g. other drive: copy from now on
                            log.info("Hardlink not possible for %s (%s); copying", src, exc)
                    if not want_link:
                        _copy_exclusive(src, candidate, sha)
                        entry.method = Method.COPY
                    entry.dest, entry.result = str(candidate), EntryResult.CREATED
                    return entry
                except FileExistsError:
                    if candidate.is_file() and sha256_file(candidate) == sha:
                        entry.dest, entry.result = str(candidate), EntryResult.SKIPPED_IDENTICAL
                        return entry
            raise OrganizerError("no free file name found")
        except (OSError, OrganizerError) as exc:
            entry.result, entry.error = EntryResult.FAILED, str(exc)
            log.warning("Could not place %s: %s", src, exc)
            return entry

    def _remove_moved_sources(self, manifest: Manifest, path: Path) -> None:
        by_source: dict[str, list[ManifestEntry]] = {}
        for e in manifest.entries:
            by_source.setdefault(e.source, []).append(e)
        pending: list[SourceRemoval] = []
        for source, entries in by_source.items():
            sha = entries[0].sha256
            if sha is None or not all(_still_valid(e) for e in entries):
                manifest.removals.append(SourceRemoval(source, sha or "", RemovalState.KEPT))
                continue
            removal = SourceRemoval(source, sha, RemovalState.PENDING)
            manifest.removals.append(removal)
            pending.append(removal)
        manifest.save(path)  # record every intent before deleting anything

        for n, removal in enumerate(pending, start=1):
            source, sha = removal.source, removal.sha256
            if n % MANIFEST_SAVE_EVERY == 0:
                manifest.save(path)
            try:
                if sha256_file(Path(source)) != sha:
                    raise OrganizerError("source changed since it was copied")
                Path(source).unlink()
                removal.state = RemovalState.DONE
            except (OSError, OrganizerError) as exc:
                removal.state = RemovalState.KEPT
                log.warning("Original kept in place %s: %s", source, exc)

    # -- main ------------------------------------------------------------------------

    def apply(
        self,
        *,
        confirm_move: bool = False,
        progress: ProgressCallback | None = None,
        cancel: CancelCheck | None = None,
    ) -> ApplyResult:
        """Execute the plan. See module docstring for the guarantees."""
        if self.plan.mode is OutputMode.MOVE and not confirm_move:
            raise OrganizerError("Moving originals requires explicit confirmation")
        self.preflight()

        manifest = Manifest(self.plan.mode, str(self.source_root), str(self.output))
        self._ensure_dir(self.output, manifest)
        path = self._new_manifest_path()
        manifest.save(path)

        items = self.plan.items
        cancelled = False
        try:
            for done, item in enumerate(items, start=1):
                if cancel is not None and cancel():
                    cancelled = True
                    break
                manifest.entries.append(self._place(item, manifest))
                if done % MANIFEST_SAVE_EVERY == 0:
                    manifest.save(path)
                if progress is not None:
                    progress(done, len(items))
        except BaseException:
            manifest.save(path)  # e.g. Ctrl+C: keep what was created undoable
            raise

        if self.plan.mode is OutputMode.MOVE:
            if cancelled:
                manifest.removals += [
                    SourceRemoval(s, self._sha.get(Path(s), ""), RemovalState.KEPT)
                    for s in dict.fromkeys(e.source for e in manifest.entries)
                ]
            else:
                manifest.save(path)
                self._remove_moved_sources(manifest, path)

        manifest.status = RunStatus.CANCELLED if cancelled else RunStatus.COMPLETED
        manifest.finished_at = _now()
        manifest.save(path)
        return ApplyResult(path, manifest)

    def _new_manifest_path(self) -> Path:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        for candidate in _candidates(self.output / f"{MANIFEST_PREFIX}{stamp}.json"):
            try:
                candidate.open("x", encoding="utf-8").close()
                return candidate
            except FileExistsError:
                continue
        raise OrganizerError("Cannot create a manifest file")  # pragma: no cover


def _still_valid(entry: ManifestEntry) -> bool:
    """True if the entry's destination exists and still has the source's content."""
    if entry.result is EntryResult.FAILED or entry.sha256 is None:
        return False
    dest = Path(entry.dest)
    return dest.is_file() and sha256_file(dest) == entry.sha256


def apply_plan(
    plan: OrganizationPlan,
    *,
    confirm_move: bool = False,
    progress: ProgressCallback | None = None,
    cancel: CancelCheck | None = None,
) -> ApplyResult:
    """Apply ``plan`` (copy by default). Returns the result with the manifest path.

    Raises:
        OrganizerError: before touching any file if the plan is unsafe or moving was
            not confirmed.
    """
    return Organizer(plan).apply(confirm_move=confirm_move, progress=progress, cancel=cancel)


# -- undo ----------------------------------------------------------------------------


@dataclass
class UndoReport:
    """What undo did (or would do, in dry-run)."""

    dry_run: bool
    restored: list[str] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)
    kept_modified: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    removed_dirs: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    already_undone: bool = False

    def summary(self) -> str:
        """Human-readable summary."""
        if self.already_undone:
            return "This manifest was already undone. Nothing to do."
        verb = "Would" if self.dry_run else "Did"
        lines = [
            f"{verb} restore {len(self.restored)} original(s) and delete "
            f"{len(self.deleted)} created file(s).",
        ]
        if self.kept_modified:
            lines.append(f"Kept {len(self.kept_modified)} file(s) modified after the run:")
            lines += [f"  {p}" for p in self.kept_modified]
        if self.missing:
            lines.append(f"{len(self.missing)} created file(s) were already gone.")
        if self.errors:
            lines.append("Errors:")
            lines += [f"  {e}" for e in self.errors]
        return "\n".join(lines)


def _same_file(a: Path, b: Path) -> bool:
    try:
        return os.path.samefile(a, b)
    except OSError:
        return False


def _created_and_intact(entry: ManifestEntry) -> bool:
    dest = Path(entry.dest)
    if entry.method is Method.LINK and _same_file(dest, Path(entry.source)):
        return True  # still a link to the original: deleting it loses nothing
    return entry.sha256 is not None and dest.is_file() and sha256_file(dest) == entry.sha256


def undo(manifest_path: Path, *, dry_run: bool = False) -> UndoReport:
    """Revert an apply run described by ``manifest_path``.

    Restores moved originals first, then deletes the files the run created (only if
    unchanged), then removes the folders it created (only if empty).
    """
    manifest_path = Path(manifest_path)
    manifest = Manifest.load(manifest_path)
    report = UndoReport(dry_run=dry_run)
    if manifest.status is RunStatus.UNDONE:
        report.already_undone = True
        return report

    created = [e for e in manifest.entries if e.result is EntryResult.CREATED]
    used_for_restore: set[str] = set()

    # 1. Put moved originals back.
    for removal in manifest.removals:
        if removal.state is RemovalState.KEPT:
            continue
        source = Path(removal.source)
        if source.exists():
            continue  # pending removal that never happened, or already restored
        candidates = [
            e
            for e in manifest.entries
            if e.source == removal.source
            and e.result is not EntryResult.FAILED
            and Path(e.dest).is_file()
            and sha256_file(Path(e.dest)) == removal.sha256
        ]
        if not candidates:
            report.errors.append(f"Cannot restore {source}: no intact copy found")
            continue
        ours = [e for e in candidates if e.result is EntryResult.CREATED]
        chosen = (ours or candidates)[0]
        report.restored.append(str(source))
        if dry_run:
            if chosen.result is EntryResult.CREATED:
                used_for_restore.add(chosen.dest)
            continue
        try:
            source.parent.mkdir(parents=True, exist_ok=True)
            if chosen.result is EntryResult.CREATED:
                try:
                    os.link(chosen.dest, source)  # same drive: instant, no copy
                except OSError:
                    _copy_exclusive(Path(chosen.dest), source, removal.sha256)
                Path(chosen.dest).unlink()
                used_for_restore.add(chosen.dest)
            else:  # pre-existing identical file that is not ours: copy, keep it
                _copy_exclusive(Path(chosen.dest), source, removal.sha256)
        except (OSError, OrganizerError) as exc:
            report.restored.pop()
            report.errors.append(f"Cannot restore {source}: {exc}")

    # 2. Delete what we created, if unchanged.
    for entry in created:
        if entry.dest in used_for_restore:
            continue
        dest = Path(entry.dest)
        if not dest.exists():
            report.missing.append(entry.dest)
            continue
        if not _created_and_intact(entry):
            report.kept_modified.append(entry.dest)
            continue
        report.deleted.append(entry.dest)
        if not dry_run:
            try:
                dest.unlink()
            except OSError as exc:
                report.deleted.pop()
                report.errors.append(f"Cannot delete {dest}: {exc}")

    # 3. Remove folders we created, deepest first, only if empty.
    if not dry_run:
        for d in sorted(manifest.created_dirs, key=lambda p: len(Path(p).parts), reverse=True):
            directory = Path(d)
            if directory.resolve() == manifest_path.parent.resolve():
                continue  # keeps the manifest (audit trail)
            try:
                directory.rmdir()
                report.removed_dirs.append(d)
            except OSError:
                pass  # not empty (user files) or already gone
        manifest.status = RunStatus.UNDONE
        manifest.finished_at = _now()
        manifest.save(manifest_path)
    return report

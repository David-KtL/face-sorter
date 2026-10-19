"""Organization plan: which photo goes to which output folder (RF-07, RF-08, RF-11).

Building a plan never touches files. The plan can be printed (dry-run) or saved as
JSON for the GUI (phase 4) and the organizer (phase 3).

Placement rules for each image:
- read error -> listed in ``errors``, not copied;
- no faces -> ``_sin_rostro/``;
- faces, but none usable -> ``_baja_calidad/``;
- each usable face in a person group -> that person's folder (once per folder);
- usable faces but none in a person group -> ``_sin_clasificar/``.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Any

from face_sorter import __version__
from face_sorter.config import (
    LOW_QUALITY_FOLDER,
    NO_FACE_FOLDER,
    PERSON_FOLDER_TEMPLATE,
    UNCLASSIFIED_FOLDER,
    OutputMode,
)
from face_sorter.core.cache import ImageStatus
from face_sorter.core.clustering import UNCLASSIFIED
from face_sorter.services.pipeline import FaceInfo, ScanResult

PLAN_FORMAT_VERSION = 1

FaceKey = tuple[Path, int]
"""Identifies a face: (image path, face index within the image)."""


class GroupKind(StrEnum):
    """Kind of output folder."""

    PERSON = "person"
    NO_FACE = "no_face"
    LOW_QUALITY = "low_quality"
    UNCLASSIFIED = "unclassified"


@dataclass
class Group:
    """An output folder and what goes into it."""

    folder: str
    kind: GroupKind
    label: int | None = None
    images: list[Path] = field(default_factory=list)
    n_faces: int = 0


@dataclass(frozen=True)
class PlanItem:
    """Copy ``source`` to ``output_root / dest``."""

    source: Path
    dest: PurePosixPath
    group: str


@dataclass(frozen=True)
class PlanFace:
    """A face and its logical group (for review in the GUI).

    A face can be in ``_sin_clasificar`` or ``_baja_calidad`` even when its photo is
    copied only to a person folder (e.g. a stranger in a group photo).
    """

    source: Path
    index: int
    bbox: tuple[float, float, float, float]
    score: float
    sharpness: float
    issues: tuple[str, ...]
    group: str


@dataclass(frozen=True)
class PlanError:
    """An image that could not be processed."""

    source: Path
    error: str


@dataclass
class OrganizationPlan:
    """The full plan. Paths in ``items[].dest`` are relative to ``output_root``."""

    source_root: Path
    output_root: Path
    mode: OutputMode
    groups: list[Group]
    items: list[PlanItem]
    faces: list[PlanFace]
    errors: list[PlanError]
    excluded_images: list[Path] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat(timespec="seconds"))

    def summary(self) -> str:
        """Human-readable summary for the terminal."""
        total = len({i.source for i in self.items}) + len(self.errors) + len(self.excluded_images)
        persons = [g for g in self.groups if g.kind is GroupKind.PERSON]
        lines = [
            f"Source: {self.source_root}",
            f"Output: {self.output_root}  (mode: {self.mode.value})",
            f"Images: {total} | person groups: {len(persons)} | "
            f"copies planned: {len(self.items)} | errors: {len(self.errors)}"
            + (f" | excluded: {len(self.excluded_images)}" if self.excluded_images else ""),
            "",
            f"{'Folder':<20} {'Images':>7} {'Faces':>7}",
            f"{'-' * 20} {'-' * 7} {'-' * 7}",
        ]
        for g in self.groups:
            lines.append(f"{g.folder:<20} {len(g.images):>7} {g.n_faces:>7}")
        if self.errors:
            lines += ["", "Unreadable images (not copied):"]
            lines += [f"  {e.source}: {e.error}" for e in self.errors]
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        """JSON-serializable representation."""
        return {
            "format_version": PLAN_FORMAT_VERSION,
            "app_version": __version__,
            "created_at": self.created_at,
            "source_root": str(self.source_root),
            "output_root": str(self.output_root),
            "mode": self.mode.value,
            "groups": [
                {
                    "folder": g.folder,
                    "kind": g.kind.value,
                    "label": g.label,
                    "n_images": len(g.images),
                    "n_faces": g.n_faces,
                }
                for g in self.groups
            ],
            "items": [
                {"source": str(i.source), "dest": str(i.dest), "group": i.group} for i in self.items
            ],
            "faces": [
                {
                    "source": str(f.source),
                    "index": f.index,
                    "bbox": list(f.bbox),
                    "score": f.score,
                    "sharpness": f.sharpness,
                    "issues": list(f.issues),
                    "group": f.group,
                }
                for f in self.faces
            ],
            "errors": [{"source": str(e.source), "error": e.error} for e in self.errors],
            "excluded_images": [str(p) for p in self.excluded_images],
        }

    def save(self, path: Path) -> None:
        """Write the plan as UTF-8 JSON."""
        Path(path).write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )


def person_folder(label: int) -> str:
    """Folder name of a person group: label 0 -> ``Persona_001``."""
    return PERSON_FOLDER_TEMPLATE.format(label + 1)


def build_plan(
    result: ScanResult,
    output_root: Path,
    mode: OutputMode = OutputMode.COPY,
    *,
    names: Mapping[int, str] | None = None,
    excluded_faces: Collection[FaceKey] = (),
    excluded_images: Collection[Path] = (),
) -> OrganizationPlan:
    """Turn a scan result into a plan. Does not touch any file.

    Args:
        names: custom folder name per cluster label (default ``Persona_NNN``). Names
            must be unique and must not clash with the special folders.
        excluded_faces: faces to ignore, as ``(image path, face index)`` (e.g. false
            detections). An image whose faces are all excluded counts as "no face".
        excluded_images: images that must not be copied at all.

    Raises:
        ValueError: if two groups would get the same folder name.
    """
    names = dict(names or {})
    excluded_f = set(excluded_faces)
    excluded_i = set(excluded_images)

    def folder_of(label: int) -> str:
        return names.get(label) or person_folder(label)

    labels = sorted(
        {
            f.label
            for f in result.faces
            if f.usable and f.label != UNCLASSIFIED and (f.image, f.index) not in excluded_f
        }
    )
    groups: dict[str, Group] = {}
    special = {
        NO_FACE_FOLDER: GroupKind.NO_FACE,
        LOW_QUALITY_FOLDER: GroupKind.LOW_QUALITY,
        UNCLASSIFIED_FOLDER: GroupKind.UNCLASSIFIED,
    }
    for label in labels:
        folder = folder_of(label)
        if folder.lower() in {g.lower() for g in groups} | {s.lower() for s in special}:
            raise ValueError(f"Duplicate or reserved group folder name: {folder}")
        groups[folder] = Group(folder, GroupKind.PERSON, label)
    for folder, kind in special.items():
        groups[folder] = Group(folder, kind)

    errors: list[PlanError] = []
    faces: list[PlanFace] = []
    placements: list[tuple[Path, str]] = []
    skipped: list[Path] = []

    for img in result.images:
        if img.status is ImageStatus.ERROR:
            errors.append(PlanError(img.path, img.error or "unknown error"))
            continue
        if img.path in excluded_i:
            skipped.append(img.path)
            continue
        kept_faces = tuple(f for f in img.faces if (f.image, f.index) not in excluded_f)
        folders = _folders_for(kept_faces, folder_of)
        for folder in folders:
            groups[folder].images.append(img.path)
            placements.append((img.path, folder))
        for f in kept_faces:
            folder = _face_group(f, folder_of)
            groups[folder].n_faces += 1
            faces.append(
                PlanFace(
                    img.path,
                    f.index,
                    f.face.bbox,
                    f.face.score,
                    f.sharpness,
                    tuple(i.value for i in f.quality.issues),
                    folder,
                )
            )

    items = _assign_names(placements)
    kept = [g for g in groups.values() if g.kind is GroupKind.PERSON or g.images or g.n_faces]
    return OrganizationPlan(
        Path(result.root),
        Path(output_root),
        mode,
        kept,
        items,
        faces,
        errors,
        excluded_images=skipped,
    )


def _face_group(face: FaceInfo, folder_of: Callable[[int], str]) -> str:
    """Logical group of a face (where the GUI shows it), even if the photo is not copied there."""
    if not face.usable:
        return LOW_QUALITY_FOLDER
    if face.label == UNCLASSIFIED:
        return UNCLASSIFIED_FOLDER
    return folder_of(face.label)


def _folders_for(faces: tuple[FaceInfo, ...], folder_of: Callable[[int], str]) -> list[str]:
    if not faces:
        return [NO_FACE_FOLDER]
    usable = [f for f in faces if f.usable]
    if not usable:
        return [LOW_QUALITY_FOLDER]
    persons = sorted({f.label for f in usable if f.label != UNCLASSIFIED})
    if persons:
        return [folder_of(label) for label in persons]
    return [UNCLASSIFIED_FOLDER]


def _assign_names(placements: list[tuple[Path, str]]) -> list[PlanItem]:
    """Give each copy a unique file name inside its folder: ``a.jpg``, ``a (2).jpg``...

    Names are compared case-insensitively (Windows). Order is by source path, so the
    result is deterministic.
    """
    taken: set[tuple[str, str]] = set()
    items: list[PlanItem] = []
    for source, folder in sorted(placements, key=lambda p: (p[1], str(p[0]).lower())):
        stem, suffix = source.stem, source.suffix
        name = source.name
        n = 1
        while (folder, name.lower()) in taken:
            n += 1
            name = f"{stem} ({n}){suffix}"
        taken.add((folder, name.lower()))
        items.append(PlanItem(source, PurePosixPath(folder, name), folder))
    return items

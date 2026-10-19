"""Review session: the user's corrections on top of a scan result (RF-09).

Pure logic, no Qt: the GUI calls these methods and redraws. Nothing here touches files.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, replace
from pathlib import Path

from face_sorter.config import (
    LOW_QUALITY_FOLDER,
    NO_FACE_FOLDER,
    UNCLASSIFIED_FOLDER,
    OutputMode,
)
from face_sorter.core.clustering import UNCLASSIFIED
from face_sorter.services.pipeline import FaceInfo, ScanResult
from face_sorter.services.plan import FaceKey, OrganizationPlan, build_plan, person_folder

MAX_NAME_LENGTH = 100
_INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_WINDOWS_RESERVED = {"CON", "PRN", "AUX", "NUL"} | {
    f"{p}{n}" for p in ("COM", "LPT") for n in range(1, 10)
}
_SPECIAL = {NO_FACE_FOLDER.lower(), LOW_QUALITY_FOLDER.lower(), UNCLASSIFIED_FOLDER.lower()}


class ReviewError(ValueError):
    """An edit was rejected (invalid or duplicate name, unknown group...)."""


def sanitize_folder_name(name: str) -> str:
    """Make ``name`` a valid folder name on Windows, macOS and Linux.

    Invalid characters become ``_``; trailing dots/spaces are removed; Windows reserved
    names (``CON``, ``COM1``...) get a ``_`` suffix.

    Raises:
        ReviewError: if the result is empty or is a special folder name.
    """
    cleaned = _INVALID_CHARS.sub("_", name).strip().rstrip(". ")[:MAX_NAME_LENGTH].strip()
    if not cleaned or set(cleaned) <= {"_", "."}:
        raise ReviewError("El nombre no puede estar vacío.")
    if cleaned.split(".")[0].upper() in _WINDOWS_RESERVED:
        cleaned += "_"
    if cleaned.lower() in _SPECIAL:
        raise ReviewError(f"«{cleaned}» es una carpeta reservada.")
    return cleaned


def face_key(face: FaceInfo) -> FaceKey:
    """Identifier of a face: ``(image path, index)``."""
    return (face.image, face.index)


@dataclass(frozen=True)
class GroupView:
    """A person group as shown in the GUI."""

    label: int
    name: str
    faces: tuple[FaceInfo, ...]

    @property
    def n_images(self) -> int:
        """Distinct photos in the group."""
        return len({f.image for f in self.faces})


class ReviewSession:
    """Editable view of a :class:`ScanResult`."""

    def __init__(self, result: ScanResult) -> None:
        self.result = result
        self._faces: dict[FaceKey, FaceInfo] = {face_key(f): f for f in result.faces}
        self._labels: dict[FaceKey, int] = {k: f.label for k, f in self._faces.items() if f.usable}
        self.names: dict[int, str] = {}
        self.excluded_faces: set[FaceKey] = set()
        self.excluded_images: set[Path] = set()
        labels = [lb for lb in self._labels.values() if lb != UNCLASSIFIED]
        self._next_label = max([result.n_clusters - 1, *labels], default=-1) + 1

    # -- queries ---------------------------------------------------------------------

    def face(self, key: FaceKey) -> FaceInfo:
        """The face with ``key``."""
        return self._faces[key]

    def label_of(self, key: FaceKey) -> int:
        """Current group of a usable face (``UNCLASSIFIED`` if none)."""
        return self._labels.get(key, UNCLASSIFIED)

    def name_of(self, label: int) -> str:
        """Folder name of a group: custom name or ``Persona_NNN``."""
        return self.names.get(label) or person_folder(label)

    def _active(self, key: FaceKey) -> bool:
        return key not in self.excluded_faces and key[0] not in self.excluded_images

    def groups(self) -> list[GroupView]:
        """Person groups with at least one face, largest first."""
        members: dict[int, list[FaceInfo]] = {}
        for key, label in self._labels.items():
            if label != UNCLASSIFIED and self._active(key):
                members.setdefault(label, []).append(self._faces[key])
        views = [GroupView(lb, self.name_of(lb), tuple(fs)) for lb, fs in members.items()]
        return sorted(views, key=lambda g: (-len(g.faces), g.label))

    def unclassified_faces(self) -> list[FaceInfo]:
        """Usable faces not assigned to any group."""
        return [
            self._faces[k]
            for k, lb in self._labels.items()
            if lb == UNCLASSIFIED and self._active(k)
        ]

    def low_quality_faces(self) -> list[FaceInfo]:
        """Faces that failed the quality filter (not clustered)."""
        return [f for k, f in self._faces.items() if not f.usable and self._active(k)]

    def excluded_face_list(self) -> list[FaceInfo]:
        """Faces excluded by the user, or belonging to excluded photos."""
        return [f for k, f in self._faces.items() if not self._active(k)]

    def no_face_images(self) -> list[Path]:
        """Photos without any detected face."""
        return [img.path for img in self.result.images if not img.faces and img.error is None]

    # -- edits -----------------------------------------------------------------------

    def _check_label(self, label: int) -> None:
        if label not in {g.label for g in self.groups()}:
            raise ReviewError(f"El grupo {label} no existe.")

    def _check_usable(self, keys: Iterable[FaceKey]) -> list[FaceKey]:
        keys = list(keys)
        bad = [k for k in keys if k not in self._labels]
        if bad:
            raise ReviewError("Los rostros de baja calidad no se pueden asignar a un grupo.")
        return keys

    def rename(self, label: int, name: str) -> str:
        """Rename a group. Returns the sanitized name actually used.

        Raises:
            ReviewError: invalid name, or another group already has it.
        """
        self._check_label(label)
        clean = sanitize_folder_name(name)
        for g in self.groups():
            if g.label != label and g.name.lower() == clean.lower():
                raise ReviewError(f"Ya existe un grupo llamado «{g.name}». Puedes unirlos.")
        self.names[label] = clean
        return clean

    def merge(self, target: int, sources: Iterable[int]) -> None:
        """Move every face of ``sources`` into ``target`` (target keeps its name)."""
        self._check_label(target)
        sources = [s for s in sources if s != target]
        for s in sources:
            self._check_label(s)
        for key, label in self._labels.items():
            if label in sources:
                self._labels[key] = target
        for s in sources:
            self.names.pop(s, None)

    def split(self, keys: Iterable[FaceKey]) -> int:
        """Move the given faces to a new group. Returns its label."""
        keys = self._check_usable(keys)
        if not keys:
            raise ReviewError("Selecciona al menos un rostro.")
        taken = {g.name.lower() for g in self.groups()}
        label = self._next_label
        while person_folder(label).lower() in taken:  # e.g. a group renamed "Persona_008"
            label += 1
        self._next_label = label + 1
        for k in keys:
            self._labels[k] = label
        return label

    def assign(self, keys: Iterable[FaceKey], label: int) -> None:
        """Move faces to an existing group, or to unclassified with ``UNCLASSIFIED``."""
        if label != UNCLASSIFIED:
            self._check_label(label)
        for k in self._check_usable(keys):
            self._labels[k] = label

    def exclude_faces(self, keys: Iterable[FaceKey]) -> None:
        """Ignore faces (e.g. false detections or strangers)."""
        self.excluded_faces.update(keys)

    def include_faces(self, keys: Iterable[FaceKey]) -> None:
        """Undo :meth:`exclude_faces` (and un-exclude their photos)."""
        for k in keys:
            self.excluded_faces.discard(k)
            self.excluded_images.discard(k[0])

    def exclude_images(self, paths: Iterable[Path]) -> None:
        """Do not copy these photos at all."""
        self.excluded_images.update(paths)

    # -- output ----------------------------------------------------------------------

    def edited_result(self) -> ScanResult:
        """The scan result with the user's group assignments applied."""
        images = tuple(
            replace(
                img,
                faces=tuple(
                    replace(f, label=self._labels.get(face_key(f), UNCLASSIFIED)) for f in img.faces
                ),
            )
            for img in self.result.images
        )
        return replace(self.result, images=images)

    def plan(self, output_root: Path, mode: OutputMode = OutputMode.COPY) -> OrganizationPlan:
        """Build the organization plan from the reviewed state."""
        return build_plan(
            self.edited_result(),
            output_root,
            mode,
            names={g.label: g.name for g in self.groups()},
            excluded_faces=self.excluded_faces,
            excluded_images=self.excluded_images,
        )

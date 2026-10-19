from __future__ import annotations

import json
from pathlib import Path, PurePosixPath

import numpy as np

from face_sorter.config import OutputMode
from face_sorter.core.cache import ImageStatus
from face_sorter.core.clustering import UNCLASSIFIED
from face_sorter.core.detector import DetectedFace
from face_sorter.core.quality import QualityIssue, QualityReport
from face_sorter.services.pipeline import FaceInfo, ImageInfo, ScanResult
from face_sorter.services.plan import GroupKind, build_plan, person_folder
from tests.fakes import LANDMARKS

ROOT = Path("/photos")
OK = QualityReport(())
BLURRY = QualityReport((QualityIssue.BLURRY,))


def _face(path: Path, index: int, label: int = UNCLASSIFIED, q: QualityReport = OK) -> FaceInfo:
    face = DetectedFace.from_values((0.0, 0.0, 90.0, 90.0), LANDMARKS, 0.9)
    return FaceInfo(path, index, face, 100.0, np.zeros(4, np.float32), q, label)


def _img(name: str, *labels: int, q: QualityReport = OK) -> ImageInfo:
    path = ROOT / name
    return ImageInfo(
        path, ImageStatus.OK, tuple(_face(path, i, lb, q) for i, lb in enumerate(labels))
    )


def _result(*images: ImageInfo, n_clusters: int = 2) -> ScanResult:
    return ScanResult(ROOT, images, n_clusters)


def _dests(plan_items: list) -> dict[str, list[str]]:  # type: ignore[type-arg]
    out: dict[str, list[str]] = {}
    for item in plan_items:
        out.setdefault(item.source.name, []).append(str(item.dest))
    return out


def test_placement_rules() -> None:
    result = _result(
        _img("ana.jpg", 0),
        _img("group.jpg", 0, 1),  # RF-07: one copy per person
        _img("ana_and_stranger.jpg", 0, UNCLASSIFIED),
        _img("stranger.jpg", UNCLASSIFIED),
        _img("blurry.jpg", UNCLASSIFIED, q=BLURRY),
        _img("landscape.jpg"),
        ImageInfo(ROOT / "broken.jpg", ImageStatus.ERROR, error="corrupt"),
    )
    plan = build_plan(result, Path("/out"))
    assert _dests(plan.items) == {
        "ana.jpg": ["Persona_001/ana.jpg"],
        "group.jpg": ["Persona_001/group.jpg", "Persona_002/group.jpg"],
        "ana_and_stranger.jpg": ["Persona_001/ana_and_stranger.jpg"],
        "stranger.jpg": ["_sin_clasificar/stranger.jpg"],
        "blurry.jpg": ["_baja_calidad/blurry.jpg"],
        "landscape.jpg": ["_sin_rostro/landscape.jpg"],
    }
    assert [(e.source.name, e.error) for e in plan.errors] == [("broken.jpg", "corrupt")]

    groups = {g.folder: (g.kind, len(g.images), g.n_faces) for g in plan.groups}
    assert groups == {
        "Persona_001": (GroupKind.PERSON, 3, 3),
        "Persona_002": (GroupKind.PERSON, 1, 1),
        "_sin_rostro": (GroupKind.NO_FACE, 1, 0),
        "_baja_calidad": (GroupKind.LOW_QUALITY, 1, 1),
        # The stranger in ana_and_stranger.jpg is reviewable but that photo is not copied here.
        "_sin_clasificar": (GroupKind.UNCLASSIFIED, 1, 2),
    }
    stranger_face = next(
        f for f in plan.faces if f.source.name == "ana_and_stranger.jpg" and f.index == 1
    )
    assert stranger_face.group == "_sin_clasificar"


def test_name_collisions_are_resolved_case_insensitively() -> None:
    result = _result(
        ImageInfo(ROOT / "a" / "IMG.jpg", ImageStatus.OK, (_face(ROOT / "a" / "IMG.jpg", 0, 0),)),
        ImageInfo(ROOT / "b" / "img.JPG", ImageStatus.OK, (_face(ROOT / "b" / "img.JPG", 0, 0),)),
        ImageInfo(ROOT / "c" / "IMG.jpg", ImageStatus.OK, (_face(ROOT / "c" / "IMG.jpg", 0, 0),)),
        n_clusters=1,
    )
    dests = [str(i.dest) for i in build_plan(result, Path("/out")).items]
    assert dests == ["Persona_001/IMG.jpg", "Persona_001/img (2).JPG", "Persona_001/IMG (3).jpg"]


def test_empty_special_groups_are_omitted() -> None:
    plan = build_plan(_result(_img("a.jpg", 0), _img("b.jpg", 0), n_clusters=1), Path("/out"))
    assert [g.folder for g in plan.groups] == ["Persona_001"]


def test_summary_and_json(tmp_path: Path) -> None:
    result = _result(
        _img("ana.jpg", 0),
        _img("luis.jpg", 1),
        ImageInfo(ROOT / "x.jpg", ImageStatus.ERROR, error="bad"),
    )
    plan = build_plan(result, tmp_path / "out", OutputMode.HARDLINK)
    text = plan.summary()
    assert "Images: 3" in text and "person groups: 2" in text and "hardlink" in text
    assert "Persona_002" in text and "bad" in text

    out = tmp_path / "plan.json"
    plan.save(out)
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["format_version"] == 1
    assert data["mode"] == "hardlink"
    assert data["items"][0] == {
        "source": str(ROOT / "ana.jpg"),
        "dest": "Persona_001/ana.jpg",
        "group": "Persona_001",
    }
    assert data["faces"][0]["group"] == "Persona_001"
    assert data["errors"] == [{"source": str(ROOT / "x.jpg"), "error": "bad"}]
    assert not (tmp_path / "out").exists()  # building/saving a plan never creates output


def test_person_folder_naming() -> None:
    assert person_folder(0) == "Persona_001"
    assert person_folder(41) == "Persona_042"
    assert PurePosixPath("Persona_001/a.jpg").parent.name == person_folder(0)

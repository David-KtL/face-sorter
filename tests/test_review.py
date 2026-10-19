from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from face_sorter.core.cache import ImageStatus
from face_sorter.core.clustering import UNCLASSIFIED
from face_sorter.core.detector import DetectedFace
from face_sorter.core.quality import QualityIssue, QualityReport
from face_sorter.services.pipeline import FaceInfo, ImageInfo, ScanResult
from face_sorter.services.review import ReviewError, ReviewSession, sanitize_folder_name
from tests.fakes import LANDMARKS

ROOT = Path("/photos")
OK = QualityReport(())


def _face(name: str, index: int, label: int, q: QualityReport = OK) -> FaceInfo:
    face = DetectedFace.from_values((0.0, 0.0, 90.0, 90.0), LANDMARKS, 0.9)
    return FaceInfo(ROOT / name, index, face, 100.0, np.zeros(4, np.float32), q, label)


def _img(name: str, *labels: int, q: QualityReport = OK) -> ImageInfo:
    return ImageInfo(
        ROOT / name, ImageStatus.OK, tuple(_face(name, i, lb, q) for i, lb in enumerate(labels))
    )


@pytest.fixture
def session() -> ReviewSession:
    result = ScanResult(
        ROOT,
        (
            _img("ana1.jpg", 0),
            _img("ana2.jpg", 0),
            _img("ana3.jpg", 0),
            _img("luis1.jpg", 1),
            _img("luis2.jpg", 1),
            _img("group.jpg", 0, 1),
            _img("stranger.jpg", UNCLASSIFIED),
            _img("blurry.jpg", UNCLASSIFIED, q=QualityReport((QualityIssue.BLURRY,))),
            _img("landscape.jpg"),
        ),
        n_clusters=2,
    )
    return ReviewSession(result)


def key(name: str, index: int = 0) -> tuple[Path, int]:
    return (ROOT / name, index)


def _dests(s: ReviewSession) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for item in s.plan(Path("/out")).items:
        out.setdefault(item.source.name, []).append(str(item.dest))
    return out


def test_initial_groups(session: ReviewSession) -> None:
    groups = session.groups()
    assert [(g.name, len(g.faces), g.n_images) for g in groups] == [
        ("Persona_001", 4, 4),
        ("Persona_002", 3, 3),
    ]
    assert [f.image.name for f in session.unclassified_faces()] == ["stranger.jpg"]
    assert [f.image.name for f in session.low_quality_faces()] == ["blurry.jpg"]
    assert session.no_face_images() == [ROOT / "landscape.jpg"]


def test_rename_changes_output_folder(session: ReviewSession) -> None:
    assert session.rename(0, "  Ana: verano/2024? ") == "Ana_ verano_2024_"
    assert _dests(session)["ana1.jpg"] == ["Ana_ verano_2024_/ana1.jpg"]


def test_rename_rejects_duplicates_case_insensitive(session: ReviewSession) -> None:
    session.rename(0, "Ana")
    with pytest.raises(ReviewError, match="Ya existe"):
        session.rename(1, "ana")
    with pytest.raises(ReviewError, match="Ya existe"):
        session.rename(0, "Persona_002")  # default name of group 1


@pytest.mark.parametrize(
    "raw, expected",
    [("CON", "CON_"), ("com1.txt", "com1.txt_"), ("Ana...", "Ana"), ("a" * 150, "a" * 100)],
)
def test_sanitize(raw: str, expected: str) -> None:
    assert sanitize_folder_name(raw) == expected


@pytest.mark.parametrize("raw", ["", "   ", "???", "_sin_rostro", "_SIN_CLASIFICAR"])
def test_sanitize_rejects(raw: str) -> None:
    with pytest.raises(ReviewError):
        sanitize_folder_name(raw)


def test_merge(session: ReviewSession) -> None:
    session.rename(0, "Ana")
    session.rename(1, "Luis")
    session.merge(0, [1])
    assert [(g.name, len(g.faces)) for g in session.groups()] == [("Ana", 7)]
    assert _dests(session)["group.jpg"] == ["Ana/group.jpg"]  # one copy only now
    assert 1 not in session.names


def test_split_and_assign(session: ReviewSession) -> None:
    new = session.split([key("ana3.jpg")])
    assert session.name_of(new) == "Persona_003"
    assert _dests(session)["ana3.jpg"] == ["Persona_003/ana3.jpg"]
    session.assign([key("stranger.jpg")], new)
    assert _dests(session)["stranger.jpg"] == ["Persona_003/stranger.jpg"]
    session.assign([key("ana3.jpg"), key("stranger.jpg")], UNCLASSIFIED)
    assert _dests(session)["stranger.jpg"] == ["_sin_clasificar/stranger.jpg"]
    assert all(g.label != new for g in session.groups())  # empty group disappears


def test_split_skips_names_already_taken(session: ReviewSession) -> None:
    session.rename(1, "Persona_003")
    new = session.split([key("ana1.jpg")])
    assert session.name_of(new) == "Persona_004"
    session.plan(Path("/out"))  # no duplicate-name error


def test_low_quality_faces_cannot_be_grouped(session: ReviewSession) -> None:
    with pytest.raises(ReviewError, match="baja calidad"):
        session.split([key("blurry.jpg")])
    with pytest.raises(ReviewError, match="al menos"):
        session.split([])
    with pytest.raises(ReviewError, match="no existe"):
        session.assign([key("ana1.jpg")], 99)


def test_exclude_and_include(session: ReviewSession) -> None:
    session.exclude_faces([key("group.jpg", 1)])  # Luis in the group photo
    assert _dests(session)["group.jpg"] == ["Persona_001/group.jpg"]
    session.exclude_faces([key("stranger.jpg")])
    assert _dests(session)["stranger.jpg"] == ["_sin_rostro/stranger.jpg"]
    assert len(session.excluded_face_list()) == 2

    session.exclude_images([ROOT / "ana1.jpg"])
    plan = session.plan(Path("/out"))
    assert "ana1.jpg" not in _dests(session)
    assert plan.excluded_images == [ROOT / "ana1.jpg"]
    assert "excluidas: 1" in plan.summary()

    session.include_faces([key("ana1.jpg"), key("group.jpg", 1)])
    assert _dests(session)["ana1.jpg"] == ["Persona_001/ana1.jpg"]
    assert len(_dests(session)["group.jpg"]) == 2


def test_edited_result_keeps_original_untouched(session: ReviewSession) -> None:
    session.merge(0, [1])
    edited = session.edited_result()
    assert {f.label for f in edited.faces if f.usable} == {0, UNCLASSIFIED}
    assert {f.label for f in session.result.faces if f.usable} == {0, 1, UNCLASSIFIED}

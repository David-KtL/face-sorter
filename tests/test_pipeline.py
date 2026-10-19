from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import numpy as np
import pytest

from face_sorter.config import Settings
from face_sorter.core.cache import FaceCache, ImageStatus
from face_sorter.core.clustering import UNCLASSIFIED
from face_sorter.core.detector import DetectedFace
from face_sorter.core.image_io import BGRImage, sha256_file
from face_sorter.services.pipeline import Pipeline, Progress, ScanCancelled
from tests.fakes import FakeDetector, FakeEmbedder, write_face_image


@pytest.fixture
def photos(tmp_path: Path) -> Path:
    root = tmp_path / "photos"
    for i in range(3):
        write_face_image(root / f"ana_{i}.png", 50)
        write_face_image(root / "sub" / f"luis_{i}.png", 150)
    write_face_image(root / "stranger.png", 220)
    write_face_image(root / "landscape.png", 0)
    (root / "broken.jpg").write_bytes(b"garbage")
    return root


@pytest.fixture
def pipeline(tmp_path: Path) -> Iterator[Pipeline]:
    settings = Settings(cache_path=tmp_path / "cache.sqlite")
    with Pipeline(settings, detector=FakeDetector(), embedder=FakeEmbedder()) as p:
        yield p


def _labels_by_name(pipeline: Pipeline, root: Path) -> dict[str, list[int]]:
    result = pipeline.run(root)
    return {img.path.name: [f.label for f in img.faces] for img in result.images}


def test_run_clusters_people(pipeline: Pipeline, photos: Path) -> None:
    result = pipeline.run(photos)
    assert result.n_clusters == 2
    by_name = {img.path.name: img for img in result.images}
    ana = {by_name[f"ana_{i}.png"].faces[0].label for i in range(3)}
    luis = {by_name[f"luis_{i}.png"].faces[0].label for i in range(3)}
    assert len(ana) == 1 and len(luis) == 1 and ana != luis
    assert by_name["stranger.png"].faces[0].label == UNCLASSIFIED
    assert by_name["landscape.png"].faces == ()
    assert by_name["broken.jpg"].status is ImageStatus.ERROR
    assert "corrupt" in (by_name["broken.jpg"].error or "")
    assert len(result.faces) == 7


def test_originals_are_untouched(pipeline: Pipeline, photos: Path) -> None:
    before = {p: sha256_file(p) for p in photos.rglob("*") if p.is_file()}
    pipeline.run(photos)
    after = {p: sha256_file(p) for p in photos.rglob("*") if p.is_file()}
    assert before == after


def test_second_run_uses_cache(pipeline: Pipeline, photos: Path) -> None:
    detector = pipeline.detector
    assert isinstance(detector, FakeDetector)
    events: list[Progress] = []
    first = _labels_by_name(pipeline, photos)
    calls = detector.calls
    second = pipeline.run(photos, progress=events.append)
    assert detector.calls == calls  # nothing re-detected
    assert all(e.from_cache for e in events)
    assert [e.done for e in events] == list(range(1, 10))
    assert {img.path.name: [f.label for f in img.faces] for img in second.images} == first


def test_cancel_keeps_processed_images_cached(pipeline: Pipeline, photos: Path) -> None:
    seen: list[Progress] = []

    def cancel() -> bool:
        return len(seen) >= 4

    with pytest.raises(ScanCancelled):
        pipeline.run(photos, progress=seen.append, cancel=cancel)
    assert pipeline.cache.count_images() == 4


def test_low_quality_faces_are_not_clustered(tmp_path: Path, photos: Path) -> None:
    settings = Settings(cache_path=tmp_path / "c2.sqlite")
    with Pipeline(settings, detector=FakeDetector(face_size=20), embedder=FakeEmbedder()) as p:
        result = p.run(photos)
    assert result.n_clusters == 0
    faces = result.faces
    assert faces and all(not f.usable and f.label == UNCLASSIFIED for f in faces)


def test_unexpected_error_in_one_image_does_not_stop_scan(tmp_path: Path, photos: Path) -> None:
    class Exploding(FakeDetector):
        def detect(self, image: BGRImage) -> list[DetectedFace]:
            if int(image[0, 0, 0]) == 220:
                raise RuntimeError("boom")
            return super().detect(image)

    settings = Settings(cache_path=tmp_path / "c3.sqlite")
    with Pipeline(settings, detector=Exploding(), embedder=FakeEmbedder()) as p:
        result = p.run(photos)
        stranger = next(i for i in result.images if i.path.name == "stranger.png")
        assert stranger.status is ImageStatus.ERROR and "boom" in (stranger.error or "")
        assert p.cache.lookup(stranger.path) is None  # retried next time
    assert result.n_clusters == 2


def test_missing_models_stop_the_scan(tmp_path: Path, photos: Path) -> None:
    settings = Settings(cache_path=tmp_path / "c4.sqlite", models_dir=tmp_path / "none")
    with Pipeline(settings) as p, pytest.raises(FileNotFoundError):
        p.run(photos)


def test_exclude_output_folder(pipeline: Pipeline, photos: Path) -> None:
    result = pipeline.run(photos, exclude=[photos / "sub"])
    assert all("luis" not in img.path.name for img in result.images)


def test_uses_shared_cache_without_closing_it(tmp_path: Path, photos: Path) -> None:
    cache = FaceCache(tmp_path / "shared.sqlite", "fake|x")
    with Pipeline(Settings(), detector=FakeDetector(), embedder=FakeEmbedder(), cache=cache) as p:
        p.run(photos)
    assert cache.count_images() == 9  # still open
    cache.close()


def test_no_usable_faces_at_all(pipeline: Pipeline, tmp_path: Path) -> None:
    root = tmp_path / "empty"
    write_face_image(root / "a.png", 0)
    result = pipeline.run(root)
    assert result.n_clusters == 0
    assert np.array_equal([len(i.faces) for i in result.images], [0])

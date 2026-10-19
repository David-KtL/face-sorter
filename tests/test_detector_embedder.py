"""Detector and embedder tests. The ones with real faces use LFW (skipped if not downloaded)."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from face_sorter.config import DetectorSettings
from face_sorter.core.detector import DetectedFace, FaceDetector
from face_sorter.core.embedder import SFaceEmbedder, cosine_similarity, l2_normalize
from face_sorter.core.image_io import load_image


@pytest.fixture(scope="module")
def detector(detector_model: Path) -> FaceDetector:
    return FaceDetector(detector_model)


@pytest.fixture(scope="module")
def embedder(recognizer_model: Path) -> SFaceEmbedder:
    return SFaceEmbedder(recognizer_model)


def test_missing_models_raise_helpful_error(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="download_models"):
        FaceDetector(tmp_path / "x.onnx")
    with pytest.raises(FileNotFoundError, match="download_models"):
        SFaceEmbedder(tmp_path / "x.onnx")


def test_blank_image_has_no_faces(detector: FaceDetector) -> None:
    assert detector.detect(np.zeros((240, 320, 3), np.uint8)) == []


def test_rejects_non_bgr(detector: FaceDetector) -> None:
    with pytest.raises(ValueError):
        detector.detect(np.zeros((10, 10), np.uint8))


def test_detected_face_roundtrip() -> None:
    lm = ((1.0, 2.0), (3.0, 4.0), (5.0, 6.0), (7.0, 8.0), (9.0, 10.0))
    face = DetectedFace.from_values((10, 20, 30, 40), lm, 0.9)
    assert face.bbox == (10, 20, 30, 40)
    assert face.landmarks == lm
    assert face.score == pytest.approx(0.9)
    assert face.min_side == 30
    with pytest.raises(ValueError):
        DetectedFace.from_values((1, 2, 3, 4), lm[:2], 0.9)


def test_l2_normalize_and_cosine() -> None:
    v = l2_normalize(np.array([3.0, 4.0]))
    assert np.allclose(v, [0.6, 0.8])
    assert v.dtype == np.float32
    assert np.array_equal(l2_normalize(np.zeros(3)), np.zeros(3))
    assert cosine_similarity(np.array([1.0, 0]), np.array([0, 2.0])) == pytest.approx(0)


def _first_photo(people: dict[str, list[Path]]) -> Path:
    return next(iter(people.values()))[0]


def test_detects_face_and_embeds(
    detector: FaceDetector, embedder: SFaceEmbedder, lfw_people: dict[str, list[Path]]
) -> None:
    image = load_image(_first_photo(lfw_people))
    faces = detector.detect(image)
    assert faces, "LFW photo should contain a face"
    face = faces[0]
    x, y, w, h = face.bbox
    # LFW photos are 250x250 with the main face roughly centred.
    assert 60 < x + w / 2 < 190 and 60 < y + h / 2 < 190
    crop = embedder.align(image, face)
    assert crop.shape == (112, 112, 3)
    emb = embedder.embed(image, face)
    assert emb.shape == (embedder.dim,)
    assert np.linalg.norm(emb) == pytest.approx(1.0, abs=1e-5)


def test_downscaling_keeps_coordinates_in_original_space(
    detector_model: Path, lfw_people: dict[str, list[Path]]
) -> None:
    image = load_image(_first_photo(lfw_people))
    big = np.asarray(cv2.resize(image, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC), np.uint8)
    got = FaceDetector(detector_model, DetectorSettings(max_input_side=500)).detect(big)[0]
    # Same work image the detector builds internally, detected without downscaling.
    half = np.asarray(cv2.resize(big, (500, 500), interpolation=cv2.INTER_AREA), np.uint8)
    ref = FaceDetector(detector_model).detect(half)[0]
    assert np.allclose(got.row[:14], ref.row[:14] * 2, atol=1e-3)
    assert got.score == pytest.approx(ref.score)

"""Phase 1 acceptance: detect faces and compute useful embeddings on LFW.

Skipped if models or LFW are missing (python scripts/download_models.py / download_lfw.py).
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from face_sorter.config import Settings
from face_sorter.core.cache import FaceCache, FaceRecord
from face_sorter.core.detector import DetectedFace, FaceDetector
from face_sorter.core.embedder import Embedding, SFaceEmbedder
from face_sorter.core.image_io import BGRImage, load_image, sha256_file
from face_sorter.core.quality import FaceMetrics, QualityIssue, assess, sharpness

LFW_CENTRE = 125.0  # LFW photos are 250x250 with the labelled face centred.


def _main_face(faces: list[DetectedFace]) -> DetectedFace:
    def dist(f: DetectedFace) -> float:
        x, y, w, h = f.bbox
        return abs(x + w / 2 - LFW_CENTRE) + abs(y + h / 2 - LFW_CENTRE)

    return min(faces, key=dist)


@pytest.fixture(scope="module")
def processed(
    detector_model: Path,
    recognizer_model: Path,
    lfw_people: dict[str, list[Path]],
) -> list[tuple[str, Path, BGRImage, DetectedFace | None, Embedding | None]]:
    detector = FaceDetector(detector_model)
    embedder = SFaceEmbedder(recognizer_model)
    out: list[tuple[str, Path, BGRImage, DetectedFace | None, Embedding | None]] = []
    for name, photos in lfw_people.items():
        for photo in photos:
            image = load_image(photo)
            faces = detector.detect(image)
            face = _main_face(faces) if faces else None
            emb = embedder.embed(image, face) if face else None
            out.append((name, photo, image, face, emb))
    return out


def test_detection_rate(processed: list) -> None:  # type: ignore[type-arg]
    detected = sum(1 for *_, face, _ in processed if face is not None)
    assert detected / len(processed) >= 0.98


def test_embeddings_identify_people(processed: list) -> None:  # type: ignore[type-arg]
    names = [n for n, *_, emb in processed if emb is not None]
    embs = np.stack([emb for *_, emb in processed if emb is not None])
    sims = embs @ embs.T
    np.fill_diagonal(sims, -np.inf)
    nearest = sims.argmax(axis=1)
    accuracy = np.mean([names[i] == names[j] for i, j in enumerate(nearest)])
    assert accuracy >= 0.95


def test_good_faces_pass_quality_and_blur_is_flagged(
    processed: list, recognizer_model: Path  # type: ignore[type-arg]
) -> None:
    # A few LFW photos are genuinely soft (e.g. Abdoulaye_Wade_0003), so most -not all-
    # originals must pass; every artificially blurred copy must be flagged.
    embedder = SFaceEmbedder(recognizer_model)
    passed = total = 0
    for *_, image, face, _ in processed:
        if face is None:
            continue
        total += 1
        crop = embedder.align(image, face)
        passed += assess(FaceMetrics(face.min_side, face.score, sharpness(crop))).ok
        blurred = embedder.align(cv2.GaussianBlur(image, (0, 0), 4), face)
        report = assess(FaceMetrics(face.min_side, face.score, sharpness(blurred)))
        assert QualityIssue.BLURRY in report.issues
    assert passed / total >= 0.9


def test_cache_roundtrip_on_real_photos(
    processed: list, tmp_path: Path, settings: Settings  # type: ignore[type-arg]
) -> None:
    fingerprint = f"{SFaceEmbedder.name}|{settings.detector.fingerprint()}"
    with FaceCache(tmp_path / "c.sqlite", fingerprint) as cache:
        for _, photo, _, face, emb in processed[:8]:
            assert face is not None and emb is not None
            cache.store_faces(photo, sha256_file(photo), [FaceRecord(face, 100.0, emb)])
        for _, photo, _, _, emb in processed[:8]:
            entry = cache.lookup(photo)
            assert entry is not None
            assert np.allclose(cache.faces(entry.id)[0].embedding, emb)

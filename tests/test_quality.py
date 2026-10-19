from __future__ import annotations

import cv2
import numpy as np
import pytest

from face_sorter.config import QualitySettings
from face_sorter.core.quality import FaceMetrics, QualityIssue, assess, sharpness


def test_sharpness_detects_blur() -> None:
    rng = np.random.default_rng(0)
    sharp = rng.integers(0, 256, (112, 112, 3), dtype=np.uint8)
    blurred = np.asarray(cv2.GaussianBlur(sharp, (15, 15), 5), dtype=np.uint8)
    assert sharpness(sharp) > 10 * sharpness(blurred)
    assert sharpness(np.full((112, 112), 128, np.uint8)) == 0.0


def test_good_face_passes() -> None:
    report = assess(FaceMetrics(min_side=100, score=0.95, sharpness=200))
    assert report.ok
    assert report.issues == ()


@pytest.mark.parametrize(
    "metrics, issue",
    [
        (FaceMetrics(min_side=10, score=0.95, sharpness=200), QualityIssue.TOO_SMALL),
        (FaceMetrics(min_side=100, score=0.5, sharpness=200), QualityIssue.LOW_SCORE),
        (FaceMetrics(min_side=100, score=0.95, sharpness=1), QualityIssue.BLURRY),
        (FaceMetrics(min_side=100, score=0.95, sharpness=float("nan")), QualityIssue.BLURRY),
    ],
)
def test_each_issue(metrics: FaceMetrics, issue: QualityIssue) -> None:
    report = assess(metrics)
    assert not report.ok
    assert report.issues == (issue,)


def test_thresholds_are_configurable() -> None:
    metrics = FaceMetrics(min_side=30, score=0.7, sharpness=10)
    assert len(assess(metrics).issues) == 3
    lenient = QualitySettings(min_face_size=20, min_score=0.5, min_sharpness=5)
    assert assess(metrics, lenient).ok

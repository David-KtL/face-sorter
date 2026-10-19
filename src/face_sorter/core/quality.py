"""Low-quality face filter: minimum size, detector confidence and sharpness (RF-04).

Raw metrics are stored in the cache and thresholds are applied afterwards, so the user
can change :class:`~face_sorter.config.QualitySettings` without re-scanning.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

import cv2
import numpy as np

from face_sorter.config import QualitySettings
from face_sorter.core.image_io import BGRImage


class QualityIssue(StrEnum):
    """Reason why a face is considered low quality."""

    TOO_SMALL = "too_small"
    LOW_SCORE = "low_score"
    BLURRY = "blurry"


@dataclass(frozen=True)
class FaceMetrics:
    """Raw, threshold-independent measurements of one face."""

    min_side: float
    score: float
    sharpness: float


@dataclass(frozen=True)
class QualityReport:
    """Result of applying the thresholds to a face's metrics."""

    issues: tuple[QualityIssue, ...]

    @property
    def ok(self) -> bool:
        """True if the face passed every check."""
        return not self.issues


def sharpness(crop: BGRImage) -> float:
    """Variance of the Laplacian of the grayscale crop. Higher means sharper.

    Use it on aligned crops of a fixed size so values are comparable across faces.
    """
    gray = crop if crop.ndim == 2 else cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def assess(metrics: FaceMetrics, settings: QualitySettings | None = None) -> QualityReport:
    """Check ``metrics`` against the thresholds in ``settings``."""
    s = settings or QualitySettings()
    issues: list[QualityIssue] = []
    if metrics.min_side < s.min_face_size:
        issues.append(QualityIssue.TOO_SMALL)
    if metrics.score < s.min_score:
        issues.append(QualityIssue.LOW_SCORE)
    if not np.isfinite(metrics.sharpness) or metrics.sharpness < s.min_sharpness:
        issues.append(QualityIssue.BLURRY)
    return QualityReport(tuple(issues))

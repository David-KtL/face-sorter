"""Face detection with OpenCV YuNet (``cv2.FaceDetectorYN``) (RF-03)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from numpy.typing import NDArray

from face_sorter.config import DetectorSettings
from face_sorter.core.image_io import BGRImage

# YuNet output row: x, y, w, h, 5 landmarks (x, y) and score -> 15 floats.
_ROW_LEN = 15


@dataclass(frozen=True)
class DetectedFace:
    """One detected face, in coordinates of the original (full-size) image.

    ``row`` is the raw 15-float YuNet row (box, 5 landmarks, score), which SFace needs
    to align the face.
    """

    row: NDArray[np.float32]

    @property
    def bbox(self) -> tuple[float, float, float, float]:
        """Bounding box as ``(x, y, width, height)``."""
        x, y, w, h = (float(v) for v in self.row[:4])
        return x, y, w, h

    @property
    def landmarks(self) -> tuple[tuple[float, float], ...]:
        """Five landmarks: right eye, left eye, nose tip, right and left mouth corners."""
        pts = self.row[4:14].reshape(5, 2)
        return tuple((float(px), float(py)) for px, py in pts)

    @property
    def score(self) -> float:
        """Detector confidence in ``[0, 1]``."""
        return float(self.row[14])

    @property
    def min_side(self) -> float:
        """Shorter side of the bounding box, in pixels."""
        return float(min(self.row[2], self.row[3]))

    @classmethod
    def from_values(
        cls,
        bbox: tuple[float, float, float, float],
        landmarks: tuple[tuple[float, float], ...],
        score: float,
    ) -> DetectedFace:
        """Rebuild a face from stored values (e.g. from the cache)."""
        flat = [*bbox, *(c for pt in landmarks for c in pt), score]
        if len(flat) != _ROW_LEN:
            raise ValueError("Expected a 4-value box and 5 landmarks")
        return cls(np.asarray(flat, dtype=np.float32))


class FaceDetector:
    """Wrapper around ``cv2.FaceDetectorYN`` that handles input size and downscaling."""

    def __init__(self, model_path: Path, settings: DetectorSettings | None = None) -> None:
        """Load the YuNet model.

        Raises:
            FileNotFoundError: if the model file is missing.
        """
        model_path = Path(model_path)
        if not model_path.is_file():
            raise FileNotFoundError(
                f"Detector model not found: {model_path}. Run: python scripts/download_models.py"
            )
        self.settings = settings or DetectorSettings()
        self._net = cv2.FaceDetectorYN.create(
            str(model_path),
            "",
            (320, 320),
            self.settings.score_threshold,
            self.settings.nms_threshold,
            self.settings.top_k,
        )

    def detect(self, image: BGRImage) -> list[DetectedFace]:
        """Detect all faces in a BGR image, sorted by score (highest first)."""
        if image.ndim != 3 or image.shape[2] != 3:
            raise ValueError("Expected a BGR image with shape (H, W, 3)")
        height, width = image.shape[:2]
        scale = min(1.0, self.settings.max_input_side / max(height, width))
        if scale < 1.0:
            size = (max(1, round(width * scale)), max(1, round(height * scale)))
            work = cv2.resize(image, size, interpolation=cv2.INTER_AREA)
        else:
            work = image

        self._net.setInputSize((work.shape[1], work.shape[0]))
        _, rows = self._net.detect(work)
        if rows is None:
            return []

        rows = np.asarray(rows, dtype=np.float32).reshape(-1, _ROW_LEN).copy()
        if scale < 1.0:
            rows[:, :14] /= scale
        rows = rows[np.argsort(-rows[:, 14])]
        return [DetectedFace(row) for row in rows]

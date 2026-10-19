"""Model-free fakes for testing the pipeline: identity is encoded in the image colour.

A synthetic image filled with grey level ``v`` (> 0) contains one face of identity ``v``;
an all-black image contains no face. The fake embedder maps each grey level to a fixed
random unit vector, so equal colours cluster together.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from face_sorter.core.detector import DetectedFace, FaceDetector
from face_sorter.core.embedder import Embedder, Embedding, l2_normalize
from face_sorter.core.image_io import BGRImage

LANDMARKS = ((30.0, 40.0), (70.0, 40.0), (50.0, 60.0), (35.0, 80.0), (65.0, 80.0))


def write_face_image(path: Path, identity: int, size: int = 100) -> Path:
    """Write a solid image whose grey level encodes ``identity`` (0 = no face)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (size, size), (identity,) * 3).save(path)
    return path


class FakeDetector(FaceDetector):
    def __init__(self, face_size: float = 80.0) -> None:  # no model to load
        self.face_size = face_size
        self.calls = 0

    def detect(self, image: BGRImage) -> list[DetectedFace]:
        self.calls += 1
        if int(image[0, 0, 0]) == 0:
            return []
        s = self.face_size
        return [DetectedFace.from_values((10.0, 10.0, s, s), LANDMARKS, 0.95)]


class FakeEmbedder(Embedder):
    name = "fake"
    dim = 16

    def align(self, image: BGRImage, face: DetectedFace) -> BGRImage:
        # Sharp noise crop, tagged with the identity in the first pixel.
        rng = np.random.default_rng(0)
        crop = rng.integers(0, 256, (112, 112, 3), dtype=np.uint8)
        crop[0, 0, 0] = image[0, 0, 0]
        return crop

    def embed_aligned(self, crop: BGRImage) -> Embedding:
        identity = int(crop[0, 0, 0])
        return l2_normalize(np.random.default_rng(identity).normal(size=self.dim))

"""Face embeddings behind a swappable :class:`Embedder` interface (RF-05, ADR 0001)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

import cv2
import numpy as np
from numpy.typing import NDArray

from face_sorter.config import RECOGNIZER_MODEL_FILENAME
from face_sorter.core.detector import DetectedFace
from face_sorter.core.image_io import BGRImage

Embedding = NDArray[np.float32]


def l2_normalize(vector: NDArray[np.floating]) -> Embedding:
    """Return ``vector`` as float32 with unit L2 norm (zero vectors are returned as-is)."""
    v = np.asarray(vector, dtype=np.float32).ravel()
    norm = float(np.linalg.norm(v))
    return np.asarray(v / norm, dtype=np.float32) if norm > 0 else v


def cosine_similarity(a: Embedding, b: Embedding) -> float:
    """Cosine similarity of two embeddings, in ``[-1, 1]``."""
    return float(np.dot(l2_normalize(a), l2_normalize(b)))


class Embedder(ABC):
    """Turns a detected face into a fixed-size, L2-normalized vector.

    Implementations must be deterministic. ``name`` identifies the model in the cache:
    if it changes, cached embeddings are invalidated.
    """

    name: str
    dim: int

    @abstractmethod
    def align(self, image: BGRImage, face: DetectedFace) -> BGRImage:
        """Return the aligned face crop the model expects."""

    @abstractmethod
    def embed_aligned(self, crop: BGRImage) -> Embedding:
        """Compute the L2-normalized embedding of an aligned crop."""

    def embed(self, image: BGRImage, face: DetectedFace) -> Embedding:
        """Align ``face`` in ``image`` and return its embedding."""
        return self.embed_aligned(self.align(image, face))


class SFaceEmbedder(Embedder):
    """OpenCV SFace (``cv2.FaceRecognizerSF``): 112x112 aligned crop -> 128-d vector."""

    name = f"sface:{RECOGNIZER_MODEL_FILENAME}"
    dim = 128

    def __init__(self, model_path: Path) -> None:
        """Load the SFace model.

        Raises:
            FileNotFoundError: if the model file is missing.
        """
        model_path = Path(model_path)
        if not model_path.is_file():
            raise FileNotFoundError(
                f"Recognizer model not found: {model_path}. "
                "Run: python scripts/download_models.py"
            )
        self._net = cv2.FaceRecognizerSF.create(str(model_path), "")

    def align(self, image: BGRImage, face: DetectedFace) -> BGRImage:
        """Similarity-transform the face to SFace's 112x112 template using its landmarks."""
        crop = self._net.alignCrop(image, face.row.reshape(1, -1))
        return np.asarray(crop, dtype=np.uint8)

    def embed_aligned(self, crop: BGRImage) -> Embedding:
        """Compute the 128-d L2-normalized embedding of a 112x112 aligned crop."""
        feature = self._net.feature(crop)
        return l2_normalize(np.asarray(feature))

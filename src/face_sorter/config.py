"""Central configuration for face-sorter.

Every path, filename and tunable default lives here so the rest of the code never
hardcodes them. Clustering thresholds are added in phase 2.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from platformdirs import user_cache_dir

APP_NAME = "face-sorter"

# Repository root (src/face_sorter/config.py -> ../../..). Used to locate ./models in dev installs.
PROJECT_ROOT = Path(__file__).resolve().parents[2]

DETECTOR_MODEL_FILENAME = "face_detection_yunet_2023mar.onnx"
RECOGNIZER_MODEL_FILENAME = "face_recognition_sface_2021dec.onnx"

SUPPORTED_EXTENSIONS: frozenset[str] = frozenset(
    {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}
)

# Decompression-bomb guard for Pillow; still allows large camera photos (~200 MP).
MAX_IMAGE_PIXELS = 200_000_000


class OutputMode(StrEnum):
    """How images are placed in the output folder. COPY is the safe default."""

    COPY = "copy"
    HARDLINK = "hardlink"
    MOVE = "move"  # Requires explicit user confirmation.


DEFAULT_OUTPUT_MODE = OutputMode.COPY


def default_models_dir() -> Path:
    """Return the directory where the ONNX models are expected."""
    return PROJECT_ROOT / "models"


def default_cache_path() -> Path:
    """Return the SQLite cache path in the per-user cache directory."""
    return Path(user_cache_dir(APP_NAME, appauthor=False)) / "cache.sqlite"


@dataclass(frozen=True)
class DetectorSettings:
    """YuNet parameters.

    ``score_threshold`` is deliberately permissive: weak faces are still detected and
    stored, and the quality filter decides later (so the user can change it without
    re-scanning). Large photos are downscaled to ``max_input_side`` for speed.
    """

    score_threshold: float = 0.6
    nms_threshold: float = 0.3
    top_k: int = 5000
    max_input_side: int = 1600

    def fingerprint(self) -> str:
        """Stable string that changes when cached detections would no longer be valid."""
        return (
            f"yunet:{DETECTOR_MODEL_FILENAME}:score={self.score_threshold}"
            f":nms={self.nms_threshold}:maxside={self.max_input_side}"
        )


@dataclass(frozen=True)
class QualitySettings:
    """Thresholds of the low-quality face filter (RF-04).

    ``min_face_size`` is in pixels of the original image (shorter side of the box).
    ``min_sharpness`` is the Laplacian variance of the aligned 112x112 face crop.
    """

    min_face_size: int = 40
    min_score: float = 0.8
    min_sharpness: float = 25.0


@dataclass(frozen=True)
class ClusteringSettings:
    """Agglomerative clustering on cosine distance (RF-06, ADR 0002).

    ``distance_threshold``: lower = stricter (splits a person into several groups);
    higher = looser (risks mixing people). Groups with fewer than ``min_cluster_size``
    faces go to the "unclassified" folder.
    """

    distance_threshold: float = 0.55
    linkage: str = "average"
    min_cluster_size: int = 2


# Output folder names (RF-08). Person groups are numbered: Persona_001, Persona_002, ...
PERSON_FOLDER_TEMPLATE = "Persona_{:03d}"
NO_FACE_FOLDER = "_sin_rostro"
LOW_QUALITY_FOLDER = "_baja_calidad"
UNCLASSIFIED_FOLDER = "_sin_clasificar"


@dataclass(frozen=True)
class Settings:
    """Runtime settings. Defaults are safe: copy mode, never touch originals."""

    models_dir: Path = field(default_factory=default_models_dir)
    cache_path: Path = field(default_factory=default_cache_path)
    output_mode: OutputMode = DEFAULT_OUTPUT_MODE
    detector: DetectorSettings = field(default_factory=DetectorSettings)
    quality: QualitySettings = field(default_factory=QualitySettings)
    clustering: ClusteringSettings = field(default_factory=ClusteringSettings)

    @property
    def detector_model_path(self) -> Path:
        """Path to the YuNet detector model."""
        return self.models_dir / DETECTOR_MODEL_FILENAME

    @property
    def recognizer_model_path(self) -> Path:
        """Path to the SFace recognizer model."""
        return self.models_dir / RECOGNIZER_MODEL_FILENAME

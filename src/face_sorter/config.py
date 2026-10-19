"""Central configuration for face-sorter.

Every path, filename and tunable default lives here so the rest of the code never
hardcodes them. Detection/quality/clustering thresholds are added in their phases.
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
class Settings:
    """Runtime settings. Defaults are safe: copy mode, never touch originals."""

    models_dir: Path = field(default_factory=default_models_dir)
    cache_path: Path = field(default_factory=default_cache_path)
    output_mode: OutputMode = DEFAULT_OUTPUT_MODE

    @property
    def detector_model_path(self) -> Path:
        """Path to the YuNet detector model."""
        return self.models_dir / DETECTOR_MODEL_FILENAME

    @property
    def recognizer_model_path(self) -> Path:
        """Path to the SFace recognizer model."""
        return self.models_dir / RECOGNIZER_MODEL_FILENAME

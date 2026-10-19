"""Central configuration for face-sorter.

Every path, filename and tunable default lives here so the rest of the code never
hardcodes them. Clustering thresholds are added in phase 2.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field, replace
from enum import StrEnum
from pathlib import Path
from typing import Any

from platformdirs import user_cache_dir, user_config_dir, user_log_dir

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

# Spanish names shown to the user.
OUTPUT_MODE_LABELS: dict[OutputMode, str] = {
    OutputMode.COPY: "copiar",
    OutputMode.HARDLINK: "enlace duro",
    OutputMode.MOVE: "mover",
}


def default_models_dir() -> Path:
    """Return the directory where the ONNX models are expected."""
    return PROJECT_ROOT / "models"


# If set, every per-user file (settings, cache, logs) lives under this folder instead of
# the platform's standard folders. Used by the tests; also handy for a portable setup.
HOME_ENV_VAR = "FACE_SORTER_HOME"


def _user_dir(kind: str) -> Path:
    home = os.environ.get(HOME_ENV_VAR)
    if home:
        return Path(home) / kind
    finder = {"cache": user_cache_dir, "config": user_config_dir, "log": user_log_dir}[kind]
    return Path(finder(APP_NAME, appauthor=False))


def default_cache_path() -> Path:
    """Return the SQLite cache path in the per-user cache directory."""
    return _user_dir("cache") / "cache.sqlite"


def settings_path() -> Path:
    """Where the user's settings are saved (JSON)."""
    return _user_dir("config") / "settings.json"


def log_path() -> Path:
    """Where the application log is written."""
    return _user_dir("log") / "face-sorter.log"


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


@dataclass(frozen=True)
class DedupeSettings:
    """Duplicate detection (RF-16 to RF-18, ADR 0006).

    ``max_distance``: two photos whose 64-bit dHash differ in at most this many bits are
    near duplicates. ``full_compare_limit``: up to this many photos, all pairs are
    compared with vectorized numpy; above it, band bucketing is used.
    """

    max_distance: int = 6
    full_compare_limit: int = 4000


# Output folder names (RF-08). Person groups are numbered: Persona_001, Persona_002, ...
PERSON_FOLDER_TEMPLATE = "Persona_{:03d}"
NO_FACE_FOLDER = "_sin_rostro"
LOW_QUALITY_FOLDER = "_baja_calidad"
UNCLASSIFIED_FOLDER = "_sin_clasificar"
# Duplicates (phase 5) are moved here, inside the analysed folder, keeping relative paths.
DUPLICATES_FOLDER = "_duplicados"
# Folder names the scanner always skips, wherever they appear.
RESERVED_DIR_NAMES: frozenset[str] = frozenset({DUPLICATES_FOLDER})

# Organizer (phase 3): manifests go to the output folder, e.g. manifest_20261019-153000.json
MANIFEST_PREFIX = "manifest_"
# The manifest is rewritten after this many file operations (and always at the end).
MANIFEST_SAVE_EVERY = 50
COPY_CHUNK_SIZE = 1 << 20  # bytes


@dataclass(frozen=True)
class Settings:
    """Runtime settings. Defaults are safe: copy mode, never touch originals."""

    models_dir: Path = field(default_factory=default_models_dir)
    cache_path: Path = field(default_factory=default_cache_path)
    output_mode: OutputMode = DEFAULT_OUTPUT_MODE
    detector: DetectorSettings = field(default_factory=DetectorSettings)
    quality: QualitySettings = field(default_factory=QualitySettings)
    clustering: ClusteringSettings = field(default_factory=ClusteringSettings)
    dedupe: DedupeSettings = field(default_factory=DedupeSettings)

    @property
    def detector_model_path(self) -> Path:
        """Path to the YuNet detector model."""
        return self.models_dir / DETECTOR_MODEL_FILENAME

    @property
    def recognizer_model_path(self) -> Path:
        """Path to the SFace recognizer model."""
        return self.models_dir / RECOGNIZER_MODEL_FILENAME


# -- user settings (RF-14) -------------------------------------------------------------

_log = logging.getLogger(__name__)

# Settings the user can change: "section.field" -> (type, minimum, maximum).
EDITABLE_SETTINGS: dict[str, tuple[type, float, float]] = {
    "clustering.distance_threshold": (float, 0.2, 0.9),
    "clustering.min_cluster_size": (int, 1, 50),
    "quality.min_face_size": (int, 10, 1000),
    "quality.min_score": (float, 0.5, 1.0),
    "quality.min_sharpness": (float, 0.0, 1000.0),
    "dedupe.max_distance": (int, 0, 20),
}


def settings_to_dict(settings: Settings) -> dict[str, Any]:
    """The user-editable part of ``settings`` as a flat JSON-friendly dict."""
    data: dict[str, Any] = {"output_mode": settings.output_mode.value}
    for key in EDITABLE_SETTINGS:
        section, name = key.split(".")
        data[key] = getattr(getattr(settings, section), name)
    return data


def settings_from_dict(data: dict[str, Any], base: Settings | None = None) -> Settings:
    """Apply validated values from ``data`` on top of ``base``.

    Unknown keys, wrong types and out-of-range values are ignored (with a warning),
    so a hand-edited or old settings file never prevents the app from starting.
    """
    settings = base or Settings()
    mode = data.get("output_mode")
    if mode is not None:
        try:
            settings = replace(settings, output_mode=OutputMode(mode))
        except ValueError:
            _log.warning("Ignoring invalid output_mode in settings: %r", mode)
    for key, value in data.items():
        if key == "output_mode":
            continue
        if key not in EDITABLE_SETTINGS:
            _log.warning("Ignoring unknown setting %r", key)
            continue
        kind, low, high = EDITABLE_SETTINGS[key]
        if isinstance(value, bool) or not isinstance(value, int | float):
            _log.warning("Ignoring non-numeric setting %s=%r", key, value)
            continue
        if kind is int and value != int(value):
            _log.warning("Ignoring non-integer setting %s=%r", key, value)
            continue
        if not low <= value <= high:
            _log.warning("Ignoring out-of-range setting %s=%r (%s..%s)", key, value, low, high)
            continue
        section, name = key.split(".")
        part = replace(getattr(settings, section), **{name: kind(value)})
        settings = replace(settings, **{section: part})
    return settings


def load_settings(path: Path | None = None) -> Settings:
    """Load the user's settings; defaults if the file is missing or unreadable."""
    path = path or settings_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return Settings()
    except (OSError, ValueError) as exc:
        _log.warning("Cannot read settings %s (%s); using defaults", path, exc)
        return Settings()
    if not isinstance(data, dict):
        _log.warning("Settings file %s is not a JSON object; using defaults", path)
        return Settings()
    return settings_from_dict(data)


def save_settings(settings: Settings, path: Path | None = None) -> Path:
    """Save the user-editable settings atomically. Returns the file path."""
    path = path or settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(settings_to_dict(settings), indent=2), encoding="utf-8")
    os.replace(tmp, path)
    return path

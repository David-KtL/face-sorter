"""Image loading with EXIF orientation (RF-02) and HEIC support. Read-only on originals."""

from __future__ import annotations

import hashlib
import io
from pathlib import Path

import numpy as np
import pillow_heif
from numpy.typing import NDArray
from PIL import Image, ImageOps, UnidentifiedImageError

from face_sorter.config import MAX_IMAGE_PIXELS

pillow_heif.register_heif_opener()
Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS

BGRImage = NDArray[np.uint8]


class ImageLoadError(Exception):
    """The file could not be read or decoded as an image."""


def decode_image(data: bytes) -> BGRImage:
    """Decode encoded image bytes into an upright BGR ``uint8`` array (H, W, 3).

    EXIF orientation is applied, and grayscale/alpha/palette images are converted
    to 3-channel colour.

    Raises:
        ImageLoadError: if the bytes are not a decodable image.
    """
    try:
        with Image.open(io.BytesIO(data)) as img:
            upright = ImageOps.exif_transpose(img)
            rgb = upright.convert("RGB")
    except UnidentifiedImageError as exc:
        raise ImageLoadError("unrecognized image format or corrupt file") from exc
    except Exception as exc:  # Pillow raises many different types for bad input.
        raise ImageLoadError(f"{type(exc).__name__}: {exc}") from exc
    array = np.asarray(rgb, dtype=np.uint8)
    return np.ascontiguousarray(array[:, :, ::-1])


def read_bytes(path: Path) -> bytes:
    """Read a file's raw bytes (opened read-only).

    Raises:
        ImageLoadError: if the file cannot be read.
    """
    try:
        return Path(path).read_bytes()
    except OSError as exc:
        raise ImageLoadError(f"{path}: {exc}") from exc


def load_image(path: Path) -> BGRImage:
    """Load ``path`` as an upright BGR array. See :func:`decode_image`."""
    try:
        return decode_image(read_bytes(path))
    except ImageLoadError as exc:
        raise ImageLoadError(f"{path}: {exc}") from exc


def sha256_bytes(data: bytes) -> str:
    """Hex SHA-256 of ``data``."""
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    """Hex SHA-256 of a file, read in chunks."""
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

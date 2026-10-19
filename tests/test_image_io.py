from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from face_sorter.core.image_io import (
    ImageLoadError,
    decode_image,
    load_image,
    sha256_bytes,
    sha256_file,
)

EXIF_ORIENTATION = 0x0112


def test_load_rgb_png_returns_bgr(tmp_path: Path) -> None:
    path = tmp_path / "red.png"
    Image.new("RGB", (4, 3), (255, 0, 0)).save(path)
    img = load_image(path)
    assert img.shape == (3, 4, 3)
    assert img.dtype == np.uint8
    assert tuple(img[0, 0]) == (0, 0, 255)  # BGR


@pytest.mark.parametrize("mode", ["RGBA", "L"])
def test_converts_to_three_channels(make_image: Callable[..., Path], mode: str) -> None:
    img = load_image(make_image(f"m_{mode}.png", mode=mode))
    assert img.shape == (48, 64, 3)


@pytest.mark.parametrize("orientation, expected_shape", [(1, (40, 80, 3)), (6, (80, 40, 3))])
def test_respects_exif_orientation(
    tmp_path: Path, orientation: int, expected_shape: tuple[int, int, int]
) -> None:
    path = tmp_path / f"o{orientation}.jpg"
    exif = Image.Exif()
    exif[EXIF_ORIENTATION] = orientation
    Image.new("RGB", (80, 40), (10, 20, 30)).save(path, exif=exif)
    assert load_image(path).shape == expected_shape


def test_loads_heic(tmp_path: Path) -> None:
    path = tmp_path / "x.heic"
    try:
        Image.new("RGB", (32, 16), (0, 128, 255)).save(path, format="HEIF")
    except Exception as exc:  # encoder not available on this platform
        pytest.skip(f"HEIF encoder not available: {exc}")
    assert load_image(path).shape == (16, 32, 3)


def test_corrupt_file_raises(tmp_path: Path) -> None:
    path = tmp_path / "broken.jpg"
    path.write_bytes(b"not an image")
    with pytest.raises(ImageLoadError, match="broken.jpg"):
        load_image(path)


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(ImageLoadError):
        load_image(tmp_path / "nope.jpg")


def test_decode_never_modifies_original(make_image: Callable[..., Path]) -> None:
    path = make_image("orig.jpg", size=(50, 50))
    before = sha256_file(path)
    load_image(path)
    assert sha256_file(path) == before == sha256_bytes(path.read_bytes())


def test_decode_image_bytes() -> None:
    with pytest.raises(ImageLoadError):
        decode_image(b"")


def test_truncated_file_raises(make_image: Callable[..., Path]) -> None:
    path = make_image("cut.jpg", size=(200, 200))
    path.write_bytes(path.read_bytes()[:300])
    with pytest.raises(ImageLoadError, match="cut.jpg"):
        load_image(path)

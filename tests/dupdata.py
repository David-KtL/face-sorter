"""Synthetic duplicate dataset (no real photos): smooth random images and their variants."""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image

EXIF_DATETIME_ORIGINAL = 0x9003
EXIF_IFD = 0x8769


def smooth_image(seed: int, size: tuple[int, int] = (320, 240)) -> Image.Image:
    """A distinct, photo-like (smooth) RGB image."""
    rng = np.random.default_rng(seed)
    small = rng.integers(0, 256, (6, 8, 3), dtype=np.uint8)
    return Image.fromarray(small, "RGB").resize(size, Image.Resampling.BICUBIC)


def save_with_date(img: Image.Image, path: Path, date: str | None = None, **kw: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if date is not None:
        exif = Image.Exif()
        exif.get_ifd(EXIF_IFD)[EXIF_DATETIME_ORIGINAL] = date
        kw["exif"] = exif
    img.save(path, **kw)  # type: ignore[arg-type]
    return path


@dataclass
class DupSet:
    root: Path
    exact: list[set[Path]] = field(default_factory=list)  # each set: identical files
    near: list[set[Path]] = field(default_factory=list)  # each set: one photo + variants
    unique: list[Path] = field(default_factory=list)


def build(root: Path, n_photos: int = 6, n_unique: int = 6) -> DupSet:
    """Each base photo gets: an exact copy, a 50 % resize, a q=40 JPEG and a PNG copy."""
    ds = DupSet(root)
    for i in range(n_photos):
        img = smooth_image(i)
        orig = save_with_date(img, root / "fotos" / f"p{i}.jpg", "2020:01:02 03:04:05", quality=92)
        copy = root / "copias" / f"p{i} - copia.jpg"
        copy.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(orig, copy)
        small = save_with_date(
            img.resize((160, 120)), root / "movil" / f"p{i}_small.jpg", quality=85
        )
        low = save_with_date(img, root / "movil" / f"p{i}_q40.jpg", quality=40)
        png = save_with_date(img, root / "export" / f"p{i}.png")
        ds.exact.append({orig, copy})
        ds.near.append({orig, copy, small, low, png})
    for j in range(n_unique):
        ds.unique.append(save_with_date(smooth_image(1000 + j), root / "otras" / f"u{j}.jpg"))
    return ds

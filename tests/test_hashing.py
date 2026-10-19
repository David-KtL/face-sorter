from __future__ import annotations

import io

import numpy as np
import pytest
from PIL import Image

from face_sorter.core.hashing import (
    compute_hashes,
    connected_groups,
    dhash,
    exif_taken_at,
    hamming,
    near_pairs,
)
from face_sorter.core.image_io import decode_image
from tests.dupdata import EXIF_DATETIME_ORIGINAL, EXIF_IFD, smooth_image


def _bgr(img: Image.Image) -> np.ndarray:
    return np.asarray(img.convert("RGB"))[:, :, ::-1].copy()


def _encode(img: Image.Image, fmt: str, **kw: object) -> bytes:
    buf = io.BytesIO()
    img.save(buf, fmt, **kw)  # type: ignore[arg-type]
    return buf.getvalue()


def test_dhash_is_robust_to_resize_and_recompression() -> None:
    img = smooth_image(1)
    h = dhash(_bgr(img))
    assert 0 <= h < 1 << 64
    assert dhash(_bgr(img)) == h  # deterministic
    for variant in (
        _encode(img.resize((160, 120)), "JPEG", quality=85),
        _encode(img, "JPEG", quality=30),
        _encode(img, "PNG"),
        _encode(img, "WEBP", quality=50),
    ):
        assert hamming(h, dhash(decode_image(variant))) <= 6


def test_dhash_separates_different_images() -> None:
    hashes = [dhash(_bgr(smooth_image(i))) for i in range(30)]
    dists = [hamming(a, b) for i, a in enumerate(hashes) for b in hashes[i + 1 :]]
    assert min(dists) > 6


def test_hamming() -> None:
    assert hamming(0, 0) == 0
    assert hamming(0b1011, 0b0001) == 2
    assert hamming(0, (1 << 64) - 1) == 64


def _random_hashes(n: int, seed: int = 0) -> list[int]:
    rng = np.random.default_rng(seed)
    hashes = [int(x) for x in rng.integers(0, 2**63, n, dtype=np.int64)]
    # plant near duplicates: flip 1..5 bits of some hashes
    for k in range(0, n // 10):
        base = hashes[k]
        flips = rng.choice(64, size=int(rng.integers(1, 6)), replace=False)
        for bit in flips:
            base ^= 1 << int(bit)
        hashes[n // 2 + k] = base
    return hashes


@pytest.mark.parametrize("max_distance", [0, 3, 6, 10])
def test_banded_search_equals_full_comparison(max_distance: int) -> None:
    hashes = _random_hashes(1500)
    full = near_pairs(hashes, max_distance, full_compare_limit=10_000)
    banded = near_pairs(hashes, max_distance, full_compare_limit=0)
    assert full == banded
    if max_distance >= 5:
        assert len(full) >= 150  # the planted pairs
    for i, j, d in full:
        assert i < j and d == hamming(hashes[i], hashes[j]) <= max_distance


def test_near_pairs_edge_cases() -> None:
    assert near_pairs([], 5) == []
    assert near_pairs([123], 5) == []
    assert near_pairs([7, 7], 0) == [(0, 1, 0)]
    with pytest.raises(ValueError):
        near_pairs([1, 2], 64)


def test_connected_groups() -> None:
    assert connected_groups(6, [(0, 1), (1, 2), (4, 5)]) == [[0, 1, 2], [4, 5]]
    assert connected_groups(3, []) == []


def test_exif_taken_at() -> None:
    exif = Image.Exif()
    exif.get_ifd(EXIF_IFD)[EXIF_DATETIME_ORIGINAL] = "2019:07:14 10:20:30"
    data = _encode(smooth_image(0), "JPEG", exif=exif)
    assert exif_taken_at(data) == "2019-07-14 10:20:30"
    assert exif_taken_at(_encode(smooth_image(0), "JPEG")) is None
    bad = Image.Exif()
    bad.get_ifd(EXIF_IFD)[EXIF_DATETIME_ORIGINAL] = "not a date"
    assert exif_taken_at(_encode(smooth_image(0), "JPEG", exif=bad)) is None
    assert exif_taken_at(b"garbage") is None


def test_compute_hashes() -> None:
    data = _encode(smooth_image(3), "PNG")
    h = compute_hashes(data)
    assert len(h.sha256) == 64 and h.phash is not None
    assert (h.width, h.height) == (320, 240)
    broken = compute_hashes(b"not an image")
    assert broken.phash is None and broken.width is None and len(broken.sha256) == 64

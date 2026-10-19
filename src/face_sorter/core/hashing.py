"""Image hashes for duplicate detection (RF-16, RF-17, ADR 0006).

- Exact duplicates: SHA-256 of the file bytes.
- Near duplicates: 64-bit dHash (difference hash) of the upright image, compared with
  the Hamming distance. Robust to resizing, recompression and format changes.

Near-duplicate search never compares pairs in pure Python: small collections use a
vectorized all-pairs comparison in blocks; large ones use band bucketing (pigeonhole
principle: with ``t + 1`` bands, two hashes at distance <= t share at least one band).
"""

from __future__ import annotations

import hashlib
import io
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

import numpy as np
from numpy.typing import NDArray
from PIL import Image

from face_sorter.core.image_io import BGRImage, ImageLoadError, decode_image

HASH_BITS = 64
_BLOCK = 1024  # rows per block in the all-pairs comparison (memory: BLOCK x n uint64)
_EXIF_IFD = 0x8769
_DATETIME_ORIGINAL = 0x9003
_DATETIME = 0x0132

Pair = tuple[int, int, int]
"""``(i, j, distance)`` with ``i < j``."""


@dataclass(frozen=True)
class ImageHashes:
    """Hashes and metadata used to find duplicates and choose which copy to keep."""

    sha256: str
    phash: int | None  # unsigned 64-bit dHash; None if the image could not be decoded
    width: int | None
    height: int | None
    taken_at: str | None  # EXIF "YYYY-MM-DD HH:MM:SS", if present


def dhash(image: BGRImage) -> int:
    """64-bit difference hash of an upright BGR image (as an unsigned int).

    Grayscale -> 9x8 (box filter) -> bit = pixel brighter than its right neighbour.
    """
    gray = (
        0.114 * image[:, :, 0].astype(np.float32)
        + 0.587 * image[:, :, 1].astype(np.float32)
        + 0.299 * image[:, :, 2].astype(np.float32)
    )
    small = Image.fromarray(gray.clip(0, 255).astype(np.uint8)).resize((9, 8), Image.Resampling.BOX)
    px = np.asarray(small, dtype=np.int16)
    bits = (px[:, 1:] > px[:, :-1]).ravel()
    return int.from_bytes(np.packbits(bits).tobytes(), "big")


def hamming(a: int, b: int) -> int:
    """Number of differing bits between two hashes."""
    return (a ^ b).bit_count()


def exif_taken_at(data: bytes) -> str | None:
    """EXIF capture date (DateTimeOriginal, else DateTime) as ``YYYY-MM-DD HH:MM:SS``."""
    try:
        with Image.open(io.BytesIO(data)) as img:
            exif = img.getexif()
            raw = exif.get_ifd(_EXIF_IFD).get(_DATETIME_ORIGINAL) or exif.get(_DATETIME)
    except Exception:  # noqa: BLE001 - metadata is optional
        return None
    if not raw:
        return None
    try:
        return datetime.strptime(str(raw).strip("\x00 "), "%Y:%m:%d %H:%M:%S").isoformat(" ")
    except ValueError:
        return None


def compute_hashes(data: bytes, image: BGRImage | None = None) -> ImageHashes:
    """Hashes of an encoded image. Pass the decoded ``image`` if you already have it.

    If the bytes cannot be decoded, only the SHA-256 is set (exact duplicates still work).
    """
    sha = hashlib.sha256(data).hexdigest()
    if image is None:
        try:
            image = decode_image(data)
        except ImageLoadError:
            return ImageHashes(sha, None, None, None, None)
    h, w = image.shape[:2]
    return ImageHashes(sha, dhash(image), w, h, exif_taken_at(data))


def _as_array(hashes: Iterable[int]) -> NDArray[np.uint64]:
    return np.fromiter(hashes, dtype=np.uint64)


def _pairs_all(h: NDArray[np.uint64], max_distance: int) -> list[Pair]:
    pairs: list[Pair] = []
    n = len(h)
    for start in range(0, n, _BLOCK):
        block = h[start : start + _BLOCK]
        dist = np.bitwise_count(block[:, None] ^ h[None, :])
        ii, jj = np.nonzero(dist <= max_distance)
        keep = start + ii < jj  # upper triangle only
        for i, j in zip((start + ii[keep]).tolist(), jj[keep].tolist(), strict=True):
            pairs.append((i, j, int(dist[i - start, j])))
    return pairs


def _pairs_banded(h: NDArray[np.uint64], max_distance: int) -> list[Pair]:
    n_bands = max_distance + 1
    edges = np.linspace(0, HASH_BITS, n_bands + 1).astype(int)
    candidates: set[tuple[int, int]] = set()
    for lo, hi in zip(edges[:-1], edges[1:], strict=True):
        width = int(hi - lo)
        mask = np.uint64((1 << width) - 1)
        band = (h >> np.uint64(lo)) & mask
        order = np.argsort(band, kind="stable")
        sorted_band = band[order]
        # Runs of equal band values are buckets of candidate pairs.
        boundaries = np.flatnonzero(np.diff(sorted_band)) + 1
        for bucket in np.split(order, boundaries):
            if len(bucket) < 2:
                continue
            idx = np.sort(bucket)
            sub = h[idx]
            dist = np.bitwise_count(sub[:, None] ^ sub[None, :])
            ii, jj = np.nonzero(np.triu(dist <= max_distance, k=1))
            candidates.update(zip(idx[ii].tolist(), idx[jj].tolist(), strict=True))
    return sorted((i, j, hamming(int(h[i]), int(h[j]))) for i, j in candidates)


def near_pairs(
    hashes: Iterable[int], max_distance: int, *, full_compare_limit: int = 4000
) -> list[Pair]:
    """All pairs of hashes at Hamming distance <= ``max_distance``, sorted.

    Uses all-pairs comparison for up to ``full_compare_limit`` hashes and band
    bucketing above it. Both give the same result.
    """
    if not 0 <= max_distance < HASH_BITS:
        raise ValueError(f"max_distance must be in [0, {HASH_BITS - 1}]")
    h = _as_array(hashes)
    if len(h) < 2:
        return []
    if len(h) <= full_compare_limit:
        return sorted(_pairs_all(h, max_distance))
    return _pairs_banded(h, max_distance)


def connected_groups(n: int, pairs: Iterable[tuple[int, int] | Pair]) -> list[list[int]]:
    """Connected components (size >= 2) of a graph with ``n`` nodes, as sorted index lists."""
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for pair in pairs:
        a, b = find(pair[0]), find(pair[1])
        if a != b:
            parent[max(a, b)] = min(a, b)
    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    return sorted((g for g in groups.values() if len(g) > 1), key=lambda g: g[0])

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import numpy as np
import pytest

from face_sorter.core.cache import FaceCache, FaceRecord, ImageStatus
from face_sorter.core.detector import DetectedFace
from face_sorter.core.embedder import l2_normalize
from face_sorter.core.image_io import sha256_file

LM = ((1.0, 2.0), (3.0, 4.0), (5.0, 6.0), (7.0, 8.0), (9.0, 10.0))


def _record(seed: int) -> FaceRecord:
    rng = np.random.default_rng(seed)
    face = DetectedFace.from_values((10.0, 20.0, 50.0 + seed, 60.0), LM, 0.9)
    return FaceRecord(face, sharpness=123.5, embedding=l2_normalize(rng.normal(size=128)))


@pytest.fixture
def photo(tmp_path: Path) -> Path:
    p = tmp_path / "Photos" / "IMG_001.JPG"
    p.parent.mkdir()
    p.write_bytes(b"fake image content")
    return p


@pytest.fixture
def cache(tmp_path: Path) -> Iterator[FaceCache]:
    c = FaceCache(tmp_path / "cache" / "c.sqlite", fingerprint="fp1")
    yield c
    c.close()


def test_miss_then_hit_with_faces_roundtrip(cache: FaceCache, photo: Path) -> None:
    assert cache.lookup(photo) is None
    records = [_record(1), _record(2)]
    entry = cache.store_faces(photo, sha256_file(photo), records)
    assert entry.status is ImageStatus.OK
    assert entry.path == str(photo.resolve())  # original case preserved

    hit = cache.lookup(photo)
    assert hit is not None and hit.id == entry.id
    faces = cache.faces(entry.id)
    assert [f.face.bbox for f in faces] == [r.face.bbox for r in records]
    assert faces[0].face.landmarks == LM
    assert np.allclose(faces[1].embedding, records[1].embedding)
    assert faces[0].metrics.sharpness == 123.5
    assert faces[0].metrics.min_side == 51.0
    assert len(list(cache.iter_faces())) == 2


def test_image_without_faces_is_cached(cache: FaceCache, photo: Path) -> None:
    entry = cache.store_faces(photo, None, [])
    assert cache.lookup(photo) is not None
    assert cache.faces(entry.id) == []


def test_modified_file_is_a_miss(cache: FaceCache, photo: Path) -> None:
    cache.store_faces(photo, sha256_file(photo), [_record(1)])
    photo.write_bytes(b"different content!")  # same length, new content
    st = photo.stat()
    os.utime(photo, ns=(st.st_atime_ns, st.st_mtime_ns + 5_000_000_000))
    assert cache.lookup(photo) is None


def test_touched_but_identical_file_is_a_hit(cache: FaceCache, photo: Path) -> None:
    entry = cache.store_faces(photo, sha256_file(photo), [_record(1)])
    new_mtime = photo.stat().st_mtime_ns + 5_000_000_000
    os.utime(photo, ns=(new_mtime, new_mtime))
    hit = cache.lookup(photo)
    assert hit is not None and hit.mtime_ns == new_mtime
    assert len(cache.faces(entry.id)) == 1


def test_restore_replaces_faces(cache: FaceCache, photo: Path) -> None:
    entry = cache.store_faces(photo, None, [_record(1), _record(2)])
    again = cache.store_faces(photo, None, [_record(3)])
    assert again.id == entry.id
    assert len(cache.faces(entry.id)) == 1


def test_errors_are_recorded(cache: FaceCache, photo: Path) -> None:
    cache.store_faces(photo, None, [_record(1)])
    entry = cache.store_error(photo, "cannot decode")
    assert entry.status is ImageStatus.ERROR and entry.error == "cannot decode"
    assert cache.faces(entry.id) == []
    assert cache.lookup(photo) is not None


def test_missing_file_lookup(cache: FaceCache, tmp_path: Path) -> None:
    assert cache.lookup(tmp_path / "gone.jpg") is None
    assert cache.get(999) is None


def test_persists_and_fingerprint_change_invalidates(tmp_path: Path, photo: Path) -> None:
    db = tmp_path / "c.sqlite"
    with FaceCache(db, "fp1") as c:
        c.store_faces(photo, None, [_record(1)])
    with FaceCache(db, "fp1") as c:
        assert c.lookup(photo) is not None
    with FaceCache(db, "fp2") as c:
        assert c.lookup(photo) is None
        assert c.count_images() == 0


def test_clear(cache: FaceCache, photo: Path) -> None:
    cache.store_faces(photo, None, [_record(1)])
    cache.clear()
    assert cache.count_images() == 0
    assert list(cache.iter_faces()) == []

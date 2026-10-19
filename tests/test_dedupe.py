"""Phase 5 acceptance: duplicates on a synthetic dataset, invariant, move + undo, trash."""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import numpy as np
import pytest

from face_sorter.config import DUPLICATES_FOLDER, Settings
from face_sorter.core.cache import SCHEMA_VERSION, FaceCache, FaceRecord
from face_sorter.core.detector import DetectedFace
from face_sorter.core.hashing import ImageHashes
from face_sorter.core.image_io import sha256_file
from face_sorter.core.scanner import scan
from face_sorter.services.dedupe import (
    DedupeError,
    DedupeScanner,
    DupKind,
    Photo,
    build_dedupe_plan,
    effective_selection,
    find_groups,
    human_size,
    keep_key,
    trash_duplicates,
)
from face_sorter.services.organizer import apply_plan, undo
from face_sorter.services.pipeline import ScanCancelled
from tests.dupdata import DupSet, build
from tests.fakes import LANDMARKS


def snapshot(root: Path) -> dict[str, str]:
    return {
        p.relative_to(root).as_posix(): sha256_file(p)
        for p in sorted(root.rglob("*"))
        if p.is_file() and DUPLICATES_FOLDER not in p.parts
    }


@pytest.fixture
def ds(tmp_path: Path) -> DupSet:
    return build(tmp_path / "photos")


@pytest.fixture
def scanner(tmp_path: Path) -> Iterator[DedupeScanner]:
    s = DedupeScanner(Settings(cache_path=tmp_path / "cache.sqlite"))
    yield s
    s.close()


# -- detection (acceptance) ---------------------------------------------------------------


def test_detects_all_exact_and_near_duplicates(ds: DupSet, scanner: DedupeScanner) -> None:
    result = scanner.run(ds.root)
    assert result.n_photos == len(ds.unique) + 5 * len(ds.exact)
    exact = [{p.path for p in g.photos} for g in result.groups if g.kind is DupKind.EXACT]
    near = [{p.path for p in g.photos} for g in result.groups if g.kind is DupKind.NEAR]
    assert sorted(map(sorted, exact)) == sorted(map(sorted, ds.exact))  # 100 % exact
    assert sorted(map(sorted, near)) == sorted(map(sorted, ds.near))  # all variants found
    grouped = {p.path for g in result.groups for p in g.photos}
    assert not grouped & set(ds.unique)  # distinct photos never grouped


def test_keep_rule_resolution_date_size_path(ds: DupSet, scanner: DedupeScanner) -> None:
    result = scanner.run(ds.root)
    for g in result.groups:
        if g.kind is DupKind.EXACT:
            # Same pixels, size and date: the shortest path wins.
            assert g.keep.path.name.startswith("p") and "copia" not in g.keep.path.name
        else:
            assert g.keep.pixels == max(p.pixels for p in g.photos)
            # The dated JPEG original wins over its heavier PNG conversion (no EXIF date).
            assert g.keep.path.parent.name == "fotos" and g.keep.path.suffix == ".jpg"
            png = next(p for p in g.photos if p.path.suffix == ".png")
            assert png.size > g.keep.size

    def photo(name: str, w: int, size: int, date: str | None) -> Photo:
        return Photo(Path(name), size, ImageHashes("x", 0, w, w, date))

    ranked = sorted(
        [
            photo("/b/long/name.jpg", 100, 10, "2020-01-01 00:00:00"),
            photo("/a.jpg", 100, 10, "2020-01-01 00:00:00"),
            photo("/old.jpg", 100, 10, "2010-01-01 00:00:00"),
            photo("/big.jpg", 100, 99, None),
            photo("/hires.jpg", 200, 1, None),
        ],
        key=keep_key,
    )
    assert [p.path.name for p in ranked] == ["hires.jpg", "old.jpg", "a.jpg", "name.jpg", "big.jpg"]


def test_default_selection_is_exact_only(ds: DupSet, scanner: DedupeScanner) -> None:
    result = scanner.run(ds.root)
    assert all(result.group(g).kind is DupKind.EXACT for g in result.default_selection())
    near_ids = [g.id for g in result.groups if g.kind is DupKind.NEAR]
    # A selected near group absorbs the exact group inside it.
    eff = effective_selection(result, result.default_selection(include_near=True))
    assert sorted(eff) == sorted(near_ids)
    assert "Use --near" in result.summary()


def test_cache_is_reused(ds: DupSet, tmp_path: Path) -> None:
    settings = Settings(cache_path=tmp_path / "c.sqlite")
    with DedupeScanner(settings) as s:
        s.run(ds.root)
    with DedupeScanner(settings) as s:
        some = next(iter(ds.exact[0]))
        assert s.cache.lookup_hashes(some) is not None


def test_cancel(ds: DupSet, scanner: DedupeScanner) -> None:
    with pytest.raises(ScanCancelled):
        scanner.run(ds.root, cancel=lambda: True)


def test_unreadable_file_is_reported(
    ds: DupSet, scanner: DedupeScanner, monkeypatch: pytest.MonkeyPatch
) -> None:
    victim = ds.unique[0]
    real = scanner.hashes

    def flaky(path: Path) -> ImageHashes:
        if path == victim:
            raise PermissionError("locked")
        return real(path)

    monkeypatch.setattr(scanner, "hashes", flaky)
    result = scanner.run(ds.root)
    assert [p for p, _ in result.errors] == [victim]


def test_corrupt_duplicates_are_still_exact(tmp_path: Path, scanner: DedupeScanner) -> None:
    root = tmp_path / "x"
    root.mkdir()
    (root / "a.jpg").write_bytes(b"broken")
    (root / "b.jpg").write_bytes(b"broken")
    result = scanner.run(root)
    assert [g.kind for g in result.groups] == [DupKind.EXACT]


# -- invariant RF-19 ----------------------------------------------------------------------


def test_override_keep_and_invariant(ds: DupSet, scanner: DedupeScanner) -> None:
    result = scanner.run(ds.root)
    g = next(g for g in result.groups if g.kind is DupKind.NEAR)
    small = next(p for p in g.photos if "small" in p.path.name)
    g.set_keep(small.path)
    assert g.keep is small and small not in g.duplicates
    with pytest.raises(DedupeError):
        g.set_keep(Path("/nope.jpg"))

    plan = build_dedupe_plan(result, [g.id])
    assert small.path not in {i.source for i in plan.items}

    small.path.unlink()  # the copy to keep disappeared
    with pytest.raises(DedupeError, match="no longer exists"):
        build_dedupe_plan(result, [g.id])


def test_changed_keep_is_refused(ds: DupSet, scanner: DedupeScanner) -> None:
    result = scanner.run(ds.root)
    g = result.group(result.default_selection()[0])
    g.keep.path.write_bytes(b"edited")
    with pytest.raises(DedupeError, match="changed"):
        build_dedupe_plan(result, [g.id])


def test_keep_removed_by_other_group_is_refused(tmp_path: Path) -> None:
    def ph(name: str, sha: str) -> Photo:
        p = tmp_path / name
        p.write_bytes(name.encode())
        return Photo(p, 1, ImageHashes(sha256_file(p), 0, 10, 10, None))

    a, b, c = ph("a.jpg", ""), ph("b.jpg", ""), ph("c.jpg", "")
    from face_sorter.services.dedupe import DedupeResult, DuplicateGroup

    g1 = DuplicateGroup("exact-001", DupKind.EXACT, [a, b], a)
    g2 = DuplicateGroup("exact-002", DupKind.EXACT, [c, a], c)  # removes a, kept by g1
    result = DedupeResult(tmp_path, [g1, g2])
    with pytest.raises(DedupeError, match="also be removed"):
        build_dedupe_plan(result, ["exact-001", "exact-002"])
    g3 = DuplicateGroup("exact-003", DupKind.EXACT, [c], c)
    with pytest.raises(DedupeError, match="nothing to remove"):
        build_dedupe_plan(DedupeResult(tmp_path, [g3]), ["exact-003"])


# -- move + undo ----------------------------------------------------------------------------


@pytest.mark.parametrize("include_near", [False, True])
def test_move_to_duplicates_and_undo(
    ds: DupSet, scanner: DedupeScanner, include_near: bool
) -> None:
    before = snapshot(ds.root)
    result = scanner.run(ds.root)
    selected = result.default_selection(include_near=include_near)
    plan = build_dedupe_plan(result, selected)
    applied = apply_plan(plan, confirm_move=True)

    after = snapshot(ds.root)
    groups = [result.group(g) for g in effective_selection(result, selected)]
    for g in groups:  # RF-19: each group keeps exactly its chosen copy
        remaining = [p for p in g.photos if p.path.relative_to(ds.root).as_posix() in after]
        assert [p.path for p in remaining] == [g.keep.path]
        for p in g.duplicates:  # moved with the same relative path
            moved = ds.root / DUPLICATES_FOLDER / p.path.relative_to(ds.root)
            assert sha256_file(moved) == p.hashes.sha256
    assert all(u.relative_to(ds.root).as_posix() in after for u in ds.unique)
    expected_moved = 6 * (4 if include_near else 1)
    assert len(before) - len(after) == expected_moved

    rescan = scanner.run(ds.root)  # _duplicados/ is never scanned
    assert all(DUPLICATES_FOLDER not in p.path.parts for g in rescan.groups for p in g.photos)

    undo(applied.manifest_path)
    assert snapshot(ds.root) == before


def test_scanner_skips_duplicates_folder(tmp_path: Path) -> None:
    (tmp_path / DUPLICATES_FOLDER / "sub").mkdir(parents=True)
    (tmp_path / DUPLICATES_FOLDER / "sub" / "x.jpg").write_bytes(b"x")
    (tmp_path / "y.jpg").write_bytes(b"y")
    assert [p.name for p in scan(tmp_path)] == ["y.jpg"]


# -- trash ----------------------------------------------------------------------------------


def test_trash_requires_confirmation_and_checks_content(ds: DupSet, scanner: DedupeScanner) -> None:
    result = scanner.run(ds.root)
    selected = result.default_selection()
    with pytest.raises(DedupeError, match="confirmation"):
        trash_duplicates(result, selected)

    sent: list[str] = []
    victim = result.group(selected[0]).duplicates[0].path
    victim.write_bytes(b"changed after the scan")
    report = trash_duplicates(result, selected, confirm=True, send=sent.append)
    assert str(victim) not in sent and [p for p, _ in report.failed] == [str(victim)]
    assert len(sent) == len(selected) - 1
    assert report.record is not None and report.record.is_file()
    assert "Recycle Bin" in report.summary()


def test_trash_uses_send2trash(
    ds: DupSet, scanner: DedupeScanner, monkeypatch: pytest.MonkeyPatch
) -> None:
    import send2trash

    sent: list[str] = []
    monkeypatch.setattr(send2trash, "send2trash", sent.append)
    result = scanner.run(ds.root)
    trash_duplicates(result, result.default_selection(), confirm=True)
    assert len(sent) == len(ds.exact)


# -- cache schema upgrade -------------------------------------------------------------------


def test_cache_v1_is_upgraded_without_losing_faces(tmp_path: Path) -> None:
    db, photo = tmp_path / "c.sqlite", tmp_path / "a.jpg"
    photo.write_bytes(b"x")
    face = DetectedFace.from_values((0.0, 0.0, 50.0, 50.0), LANDMARKS, 0.9)
    with FaceCache(db, "fp") as c:
        c.store_faces(photo, None, [FaceRecord(face, 10.0, np.ones(4, np.float32))])
    con = sqlite3.connect(db)  # turn it into a v1 database
    con.execute("DROP TABLE image_hashes")
    con.execute("UPDATE meta SET value = '1' WHERE key = 'schema_version'")
    con.commit()
    con.close()

    with FaceCache(db, "fp") as c:
        assert c.count_images() == 1  # faces kept
        c.store_hashes(photo, ImageHashes("s", (1 << 64) - 1, 1, 1, None))
        assert c.lookup_hashes(photo) == ImageHashes("s", (1 << 64) - 1, 1, 1, None)
        assert c._meta("schema_version") == SCHEMA_VERSION
        os.utime(photo, ns=(1, 1))
        assert c.lookup_hashes(photo) is None  # file changed
        c.clear()


def test_find_groups_without_phash() -> None:
    photos = [
        Photo(Path(f"/{i}.jpg"), 1, ImageHashes(str(i), None, None, None, None)) for i in range(3)
    ]
    assert find_groups(photos, 6) == []


def test_human_size() -> None:
    assert [human_size(n) for n in (512, 1536, 5 * 1024**2, 3 * 1024**3)] == [
        "512 B",
        "1.5 KB",
        "5.0 MB",
        "3.0 GB",
    ]

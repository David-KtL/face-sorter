from __future__ import annotations

from pathlib import Path

import pytest

from face_sorter.core.scanner import is_supported, scan


def _touch(root: Path, *names: str) -> None:
    for name in names:
        p = root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"x")


def test_scan_is_recursive_sorted_and_filters_extensions(tmp_path: Path) -> None:
    _touch(tmp_path, "b.JPG", "a.png", "notes.txt", "sub/c.heic", "sub/deeper/d.webp", "e.jpeg")
    found = [p.relative_to(tmp_path).as_posix() for p in scan(tmp_path)]
    assert found == ["a.png", "b.JPG", "e.jpeg", "sub/c.heic", "sub/deeper/d.webp"]


def test_scan_skips_hidden_and_excluded(tmp_path: Path) -> None:
    _touch(tmp_path, "keep.jpg", ".hidden.jpg", ".thumbs/x.jpg", "out/copied.jpg")
    found = [p.name for p in scan(tmp_path, exclude=[tmp_path / "out"])]
    assert found == ["keep.jpg"]


def test_scan_custom_extensions(tmp_path: Path) -> None:
    _touch(tmp_path, "a.jpg", "b.png")
    assert [p.name for p in scan(tmp_path, extensions=[".PNG"])] == ["b.png"]


def test_scan_rejects_non_folder(tmp_path: Path) -> None:
    with pytest.raises(NotADirectoryError):
        list(scan(tmp_path / "missing"))


def test_is_supported() -> None:
    assert is_supported(Path("x.HEIC"))
    assert not is_supported(Path("x.gif"))

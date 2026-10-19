"""CLI ``scan`` tests. The end-to-end one uses real models and LFW photos (skipped if missing)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from face_sorter.__main__ import EXIT_ERROR, EXIT_OK, main
from face_sorter.core.image_io import sha256_file
from tests.fakes import write_face_image


def test_missing_input_folder(tmp_path: Path) -> None:
    assert main(["scan", str(tmp_path / "nope"), "--out", str(tmp_path / "o"), "--dry-run"]) == (
        EXIT_ERROR
    )


def test_output_must_differ_from_input(tmp_path: Path) -> None:
    assert main(["scan", str(tmp_path), "--out", str(tmp_path), "--dry-run"]) == EXIT_ERROR


def test_move_without_tty_needs_yes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    argv = ["scan", str(tmp_path), "--out", str(tmp_path / "o"), "--mode", "move"]
    assert main(argv) == EXIT_ERROR
    assert not (tmp_path / "o").exists()


def test_scan_dry_run_end_to_end(
    tmp_path: Path,
    lfw_people: dict[str, list[Path]],
    detector_model: Path,
    recognizer_model: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    src = tmp_path / "photos"
    people = list(lfw_people.items())[:3]
    for name, photos in people:
        for photo in photos[:3]:
            dest = src / name[:3] / photo.name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(photo, dest)
    (src / "broken.jpg").write_bytes(b"garbage")
    before = {p: sha256_file(p) for p in src.rglob("*") if p.is_file()}

    out = tmp_path / "out"
    plan_file = tmp_path / "plan.json"
    argv = ["scan", str(src), "--out", str(out), "--dry-run", "-q"]
    argv += ["--cache", str(tmp_path / "c.sqlite"), "--plan", str(plan_file)]
    assert main(argv) == EXIT_OK

    stdout = capsys.readouterr().out
    assert "DRY RUN" in stdout and "Persona_003" in stdout
    assert not out.exists()  # dry-run creates nothing
    assert before == {p: sha256_file(p) for p in src.rglob("*") if p.is_file()}

    plan = json.loads(plan_file.read_text(encoding="utf-8"))
    by_group: dict[str, set[str]] = {}
    for item in plan["items"]:
        by_group.setdefault(item["group"], set()).add(Path(item["source"]).parent.name)
    persons = {g: dirs for g, dirs in by_group.items() if g.startswith("Persona_")}
    assert len(persons) == 3
    assert all(len(dirs) == 1 for dirs in persons.values())  # each group = one person
    assert [Path(e["source"]).name for e in plan["errors"]] == ["broken.jpg"]


def test_missing_models_is_a_clear_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import face_sorter.__main__ as cli
    from face_sorter.config import Settings

    monkeypatch.setattr(cli, "Settings", lambda: Settings(models_dir=tmp_path / "none"))
    src = tmp_path / "src"
    src.mkdir()
    write_face_image(src / "a.png", 100)  # valid image -> models are needed
    argv = ["scan", str(src), "--out", str(tmp_path / "o"), "--dry-run", "-q"]
    assert main(argv + ["--cache", str(tmp_path / "c.sqlite")]) == EXIT_ERROR
    assert "download_models" in capsys.readouterr().err


def _copy_people(lfw_people: dict[str, list[Path]], src: Path) -> dict[str, str]:
    for name, photos in list(lfw_people.items())[:2]:
        for photo in photos[:2]:
            dest = src / name[:3] / photo.name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(photo, dest)
    return {p.relative_to(src).as_posix(): sha256_file(p) for p in src.rglob("*") if p.is_file()}


def test_scan_apply_then_undo_end_to_end(
    tmp_path: Path,
    lfw_people: dict[str, list[Path]],
    detector_model: Path,
    recognizer_model: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    src, out = tmp_path / "photos", tmp_path / "out"
    before = _copy_people(lfw_people, src)
    argv = ["scan", str(src), "--out", str(out), "-q", "--cache", str(tmp_path / "c.sqlite")]
    assert main(argv) == EXIT_OK
    assert "Created: 4" in capsys.readouterr().out
    copies = sorted(p.relative_to(out).as_posix() for p in out.rglob("*.jpg"))
    assert len(copies) == 4 and all(c.startswith("Persona_00") for c in copies)
    assert before == {
        p.relative_to(src).as_posix(): sha256_file(p) for p in src.rglob("*") if p.is_file()
    }

    manifest = next(out.glob("manifest_*.json"))
    assert main(["undo", str(manifest), "--dry-run"]) == EXIT_OK
    assert len(list(out.rglob("*.jpg"))) == 4
    assert main(["undo", str(manifest)]) == EXIT_OK
    assert list(out.rglob("*.jpg")) == []


def test_scan_move_asks_and_respects_no(
    tmp_path: Path,
    lfw_people: dict[str, list[Path]],
    detector_model: Path,
    recognizer_model: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    src, out = tmp_path / "photos", tmp_path / "out"
    before = _copy_people(lfw_people, src)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt: "n")
    argv = ["scan", str(src), "--out", str(out), "-q", "--mode", "move"]
    assert main(argv + ["--cache", str(tmp_path / "c.sqlite")]) == EXIT_OK
    assert "Nothing was changed" in capsys.readouterr().out
    assert not out.exists()
    assert len(before) == sum(1 for p in src.rglob("*") if p.is_file())

    monkeypatch.setattr("builtins.input", lambda prompt: "s")
    assert main(argv + ["--cache", str(tmp_path / "c.sqlite")]) == EXIT_OK
    assert [p for p in src.rglob("*") if p.is_file()] == []
    manifest = next(out.glob("manifest_*.json"))
    assert main(["undo", str(manifest)]) == EXIT_OK
    assert before == {
        p.relative_to(src).as_posix(): sha256_file(p) for p in src.rglob("*") if p.is_file()
    }

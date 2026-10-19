"""CLI ``scan`` tests. The end-to-end one uses real models and LFW photos (skipped if missing)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from face_sorter.__main__ import EXIT_ERROR, EXIT_NOT_IMPLEMENTED, EXIT_OK, main
from face_sorter.core.image_io import sha256_file
from tests.fakes import write_face_image


def test_missing_input_folder(tmp_path: Path) -> None:
    assert main(["scan", str(tmp_path / "nope"), "--out", str(tmp_path / "o"), "--dry-run"]) == (
        EXIT_ERROR
    )


def test_output_must_differ_from_input(tmp_path: Path) -> None:
    assert main(["scan", str(tmp_path), "--out", str(tmp_path), "--dry-run"]) == EXIT_ERROR


def test_applying_is_not_available_yet(tmp_path: Path) -> None:
    # Without --dry-run nothing may be touched until the organizer exists (phase 3).
    assert main(["scan", str(tmp_path), "--out", str(tmp_path / "o")]) == EXIT_NOT_IMPLEMENTED
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

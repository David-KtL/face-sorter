"""User settings (RF-14), CSV report (RF-15) and logging (RNF-07)."""

from __future__ import annotations

import csv
import json
import logging
from pathlib import Path, PurePosixPath

import pytest

from face_sorter.__main__ import main
from face_sorter.config import (
    HOME_ENV_VAR,
    OutputMode,
    Settings,
    default_cache_path,
    load_settings,
    log_path,
    save_settings,
    settings_from_dict,
    settings_path,
    settings_to_dict,
)
from face_sorter.logging_setup import setup_logging
from face_sorter.services.plan import OrganizationPlan, PlanError, PlanFace, PlanItem
from face_sorter.services.report import CSV_COLUMNS, plan_rows, write_csv

# -- settings ------------------------------------------------------------------------------


def test_user_dirs_follow_home_env(isolated_home: Path) -> None:
    assert settings_path().is_relative_to(isolated_home)
    assert default_cache_path().is_relative_to(isolated_home)
    assert log_path().is_relative_to(isolated_home)


def test_save_and_load_roundtrip() -> None:
    assert load_settings() == Settings()  # no file yet: defaults
    s = settings_from_dict(
        {
            "clustering.distance_threshold": 0.5,
            "quality.min_face_size": 60,
            "dedupe.max_distance": 4,
            "output_mode": "hardlink",
        }
    )
    path = save_settings(s)
    assert path == settings_path()
    loaded = load_settings()
    assert loaded.clustering.distance_threshold == 0.5
    assert loaded.quality.min_face_size == 60
    assert loaded.dedupe.max_distance == 4
    assert loaded.output_mode is OutputMode.HARDLINK
    assert settings_to_dict(loaded)["quality.min_face_size"] == 60


@pytest.mark.parametrize(
    "data",
    [
        {"clustering.distance_threshold": 5.0},  # out of range
        {"quality.min_face_size": 40.5},  # not an integer
        {"quality.min_score": "high"},  # not a number
        {"quality.min_score": True},  # bool is not a number here
        {"unknown.key": 1},
        {"output_mode": "teleport"},
    ],
)
def test_invalid_values_are_ignored(
    data: dict[str, object], caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING):
        assert settings_from_dict(data) == Settings()
    assert caplog.records


@pytest.mark.parametrize("content", ["{broken json", "[1, 2]"])
def test_corrupt_settings_file_falls_back_to_defaults(content: str) -> None:
    settings_path().parent.mkdir(parents=True, exist_ok=True)
    settings_path().write_text(content, encoding="utf-8")
    assert load_settings() == Settings()


def test_cli_uses_saved_settings(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    save_settings(settings_from_dict({"output_mode": "move"}))
    src = tmp_path / "src"
    src.mkdir()
    # Saved mode is "move": without a terminal it must refuse instead of moving.
    assert main(["scan", str(src), "--out", str(tmp_path / "o")]) == 1
    assert "mover" in capsys.readouterr().err


# -- CSV -----------------------------------------------------------------------------------


def _plan() -> OrganizationPlan:
    root = Path("/fotos")
    items = [
        PlanItem(root / "grupo.jpg", PurePosixPath("Ana/grupo.jpg"), "Ana"),
        PlanItem(root / "grupo.jpg", PurePosixPath("Luis/grupo.jpg"), "Luis"),
        PlanItem(root / "paisaje.jpg", PurePosixPath("_sin_rostro/paisaje.jpg"), "_sin_rostro"),
    ]
    faces = [
        PlanFace(root / "grupo.jpg", 0, (0, 0, 1, 1), 0.9, 100, (), "Ana"),
        PlanFace(root / "grupo.jpg", 1, (0, 0, 1, 1), 0.9, 100, (), "Luis"),
    ]
    errors = [PlanError(root / "roto.jpg", "archivo dañado")]
    return OrganizationPlan(
        root,
        Path("/salida"),
        OutputMode.COPY,
        [],
        items,
        faces,
        errors,
        excluded_images=[root / "excluida.jpg"],
    )


def test_csv_rows() -> None:
    rows = plan_rows(_plan())
    assert [(Path(r["foto"]).name, r["grupo"], r["n_rostros"], r["estado"]) for r in rows] == [
        ("excluida.jpg", "", "0", "excluida"),
        ("grupo.jpg", "Ana", "2", "copiar"),
        ("grupo.jpg", "Luis", "2", "copiar"),
        ("paisaje.jpg", "_sin_rostro", "0", "copiar"),
        ("roto.jpg", "", "0", "error: archivo dañado"),
    ]


def test_write_csv_opens_in_spanish_excel(tmp_path: Path) -> None:
    out = tmp_path / "reporte.csv"
    assert write_csv(_plan(), out) == 5
    raw = out.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")  # UTF-8 BOM
    with out.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f, delimiter=";"))
    assert rows[0] == CSV_COLUMNS
    assert rows[-1][-1] == "error: archivo dañado"


# -- logging -------------------------------------------------------------------------------


def test_setup_logging_writes_file(tmp_path: Path) -> None:
    path = setup_logging(file=tmp_path / "logs" / "app.log")
    assert path is not None
    logging.getLogger("face_sorter.test").info("hola log")
    for h in logging.getLogger().handlers:
        h.flush()
    assert "hola log" in path.read_text(encoding="utf-8")
    setup_logging(file=tmp_path / "logs" / "app.log")  # idempotent: no duplicate handlers
    ours = [h for h in logging.getLogger().handlers if getattr(h, "_face_sorter", False)]
    assert len(ours) == 2


def test_setup_logging_survives_unwritable_dir(tmp_path: Path) -> None:
    blocker = tmp_path / "file"
    blocker.write_text("x")
    assert setup_logging(file=blocker / "sub" / "app.log") is None


def test_home_env_var_name() -> None:
    assert HOME_ENV_VAR == "FACE_SORTER_HOME"
    assert json.loads(json.dumps(settings_to_dict(Settings())))["output_mode"] == "copy"

"""Smoke tests: the package imports and the CLI is wired up."""

from __future__ import annotations

from pathlib import Path

import pytest

import face_sorter
from face_sorter.__main__ import EXIT_NOT_IMPLEMENTED, build_parser, main
from face_sorter.config import OutputMode, Settings


def test_version_is_defined() -> None:
    assert face_sorter.__version__


def test_subpackages_import() -> None:
    import face_sorter.core  # noqa: F401
    import face_sorter.gui  # noqa: F401
    import face_sorter.services  # noqa: F401


def test_default_settings_are_safe() -> None:
    settings = Settings()
    assert settings.output_mode is OutputMode.COPY
    assert settings.detector_model_path.suffix == ".onnx"
    assert settings.recognizer_model_path.suffix == ".onnx"


def test_scan_parses_with_safe_defaults(tmp_path: Path) -> None:
    args = build_parser().parse_args(["scan", str(tmp_path), "--out", str(tmp_path / "out")])
    assert args.command == "scan"
    assert args.mode == "copy"
    assert args.dry_run is False


@pytest.mark.parametrize("argv", [["gui"]])
def test_commands_not_implemented_yet(argv: list[str]) -> None:
    assert main(argv) == EXIT_NOT_IMPLEMENTED


def test_command_is_required() -> None:
    with pytest.raises(SystemExit):
        main([])


def test_undo_missing_manifest_is_an_error(tmp_path: Path) -> None:
    assert main(["undo", str(tmp_path / "manifest_x.json")]) == 1

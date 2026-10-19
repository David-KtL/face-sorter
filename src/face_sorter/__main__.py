"""Command-line interface: ``face-sorter scan | gui | undo``.

Phase 0: the commands are wired up but have no logic yet.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from face_sorter import __version__
from face_sorter.config import DEFAULT_OUTPUT_MODE, OutputMode

EXIT_NOT_IMPLEMENTED = 2


def _not_implemented(command: str, phase: int) -> int:
    print(f"'{command}' is not implemented yet (planned for phase {phase}).", file=sys.stderr)
    return EXIT_NOT_IMPLEMENTED


def _cmd_scan(args: argparse.Namespace) -> int:
    return _not_implemented("scan", 2)


def _cmd_gui(args: argparse.Namespace) -> int:
    return _not_implemented("gui", 4)


def _cmd_undo(args: argparse.Namespace) -> int:
    return _not_implemented("undo", 3)


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser with the ``scan``, ``gui`` and ``undo`` subcommands."""
    parser = argparse.ArgumentParser(
        prog="face-sorter",
        description="Group photos by person into folders (100% local).",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    scan = sub.add_parser("scan", help="Scan a folder and group its photos by person.")
    scan.add_argument("input", type=Path, help="Folder with the photos (read recursively).")
    scan.add_argument("--out", type=Path, required=True, help="Output folder.")
    scan.add_argument(
        "--mode",
        choices=[m.value for m in OutputMode],
        default=DEFAULT_OUTPUT_MODE.value,
        help="copy (default), hardlink or move (move asks for confirmation).",
    )
    scan.add_argument(
        "--dry-run", action="store_true", help="Show what would be done without touching files."
    )
    scan.set_defaults(func=_cmd_scan)

    gui = sub.add_parser("gui", help="Open the graphical interface.")
    gui.set_defaults(func=_cmd_gui)

    undo = sub.add_parser("undo", help="Revert the operations recorded in a manifest.")
    undo.add_argument("manifest", type=Path, help="Path to a manifest_*.json file.")
    undo.add_argument(
        "--dry-run", action="store_true", help="Show what would be reverted without doing it."
    )
    undo.set_defaults(func=_cmd_undo)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for the ``face-sorter`` command."""
    args = build_parser().parse_args(argv)
    func: Callable[[argparse.Namespace], int] = args.func
    return func(args)


if __name__ == "__main__":
    raise SystemExit(main())

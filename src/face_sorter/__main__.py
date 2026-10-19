"""Command-line interface: ``face-sorter scan | dedupe | gui | undo``."""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Callable, Sequence
from dataclasses import replace
from pathlib import Path

from face_sorter import __version__
from face_sorter.config import DEFAULT_OUTPUT_MODE, OutputMode, Settings

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_NOT_IMPLEMENTED = 2
EXIT_INTERRUPTED = 130


def _not_implemented(what: str, phase: int) -> int:
    print(f"{what} is not implemented yet (planned for phase {phase}).", file=sys.stderr)
    return EXIT_NOT_IMPLEMENTED


def _error(message: str) -> int:
    print(f"error: {message}", file=sys.stderr)
    return EXIT_ERROR


def _settings_from_args(args: argparse.Namespace) -> Settings:
    settings = Settings()
    if args.cache is not None:
        settings = replace(settings, cache_path=args.cache)
    if args.threshold is not None:
        settings = replace(
            settings, clustering=replace(settings.clustering, distance_threshold=args.threshold)
        )
    return replace(settings, output_mode=OutputMode(args.mode))


def _cmd_scan(args: argparse.Namespace) -> int:
    source: Path = args.input.resolve()
    output: Path = args.out.resolve()
    if not source.is_dir():
        return _error(f"input folder not found: {source}")
    if output == source:
        return _error("the output folder must be different from the input folder")
    settings = _settings_from_args(args)
    moving = settings.output_mode is OutputMode.MOVE and not args.dry_run
    if moving and not args.yes and not sys.stdin.isatty():
        return _error("--mode move needs confirmation: run it interactively or add --yes")

    # Heavy imports (OpenCV, scikit-learn) only when actually scanning.
    from tqdm import tqdm

    from face_sorter.services.organizer import OrganizerError, apply_plan
    from face_sorter.services.pipeline import Pipeline, Progress
    from face_sorter.services.plan import build_plan

    with tqdm(unit="img", disable=args.quiet or None, file=sys.stderr) as bar:

        def on_progress(p: Progress) -> None:
            bar.total = p.total
            bar.update(1)

        try:
            with Pipeline(settings) as pipeline:
                result = pipeline.run(source, exclude=[output], progress=on_progress)
        except KeyboardInterrupt:
            print("\nInterrupted. Processed images are cached; run again to resume.")
            return EXIT_INTERRUPTED
        except FileNotFoundError as exc:  # missing models
            return _error(str(exc))

    plan = build_plan(result, output, settings.output_mode)
    if args.dry_run:
        print("DRY RUN: no files were copied, moved or modified.\n")
    print(plan.summary())
    if args.plan is not None:
        plan.save(args.plan)
        print(f"\nPlan saved to {args.plan}")
    if args.dry_run:
        return EXIT_OK

    if moving and not args.yes and not _confirm_move(len({i.source for i in plan.items})):
        print("Cancelled. Nothing was changed.")
        return EXIT_OK

    print()
    try:
        with tqdm(total=len(plan.items), unit="file", disable=args.quiet or None) as bar:
            applied = apply_plan(
                plan,
                confirm_move=moving,
                progress=lambda done, total: bar.update(done - bar.n),
            )
    except OrganizerError as exc:
        return _error(f"{exc}. Nothing was changed.")
    except KeyboardInterrupt:
        print("\nInterrupted. Use 'face-sorter undo' with the manifest in the output folder.")
        return EXIT_INTERRUPTED
    print(applied.summary())
    print(f'Undo with: face-sorter undo "{applied.manifest_path}"')
    return EXIT_OK


def _confirm_move(n_sources: int) -> bool:
    """Ask before moving originals (golden rule). Default answer is No."""
    prompt = (
        f"\nMOVE mode: {n_sources} original photo(s) will be moved out of the source folder.\n"
        "They can be restored with 'face-sorter undo'. Continue? [s/N] "
    )
    return _ask(prompt)


def _ask(prompt: str) -> bool:
    """Yes/no question on the terminal. Default answer is No."""
    try:
        answer = input(prompt)
    except EOFError:
        return False
    return answer.strip().lower() in {"s", "si", "sí", "y", "yes"}


def _cmd_dedupe(args: argparse.Namespace) -> int:
    folder: Path = args.folder.resolve()
    if not folder.is_dir():
        return _error(f"folder not found: {folder}")
    acting = not args.dry_run
    if acting and not args.yes and not sys.stdin.isatty():
        return _error("dedupe needs confirmation: run it interactively, use --dry-run or --yes")

    from tqdm import tqdm

    from face_sorter.config import DUPLICATES_FOLDER
    from face_sorter.services.dedupe import (
        DedupeError,
        DedupeScanner,
        build_dedupe_plan,
        effective_selection,
        trash_duplicates,
    )
    from face_sorter.services.organizer import OrganizerError, apply_plan

    settings = Settings()
    if args.cache is not None:
        settings = replace(settings, cache_path=args.cache)
    if args.max_distance is not None:
        settings = replace(
            settings, dedupe=replace(settings.dedupe, max_distance=args.max_distance)
        )

    with tqdm(unit="img", disable=args.quiet or None, file=sys.stderr) as bar:

        def on_progress(done: int, total: int) -> None:
            bar.total = total
            bar.update(1)

        try:
            with DedupeScanner(settings) as scanner:
                result = scanner.run(folder, progress=on_progress)
        except KeyboardInterrupt:
            print("\nInterrupted. Hashes computed so far are cached.")
            return EXIT_INTERRUPTED

    selected = effective_selection(result, result.default_selection(include_near=args.near))
    if args.dry_run:
        print("DRY RUN: no files were moved or deleted.\n")
    print(result.summary(selected))
    n_files = sum(len(result.group(g).duplicates) for g in selected)
    if not acting:
        return EXIT_OK
    if n_files == 0:
        print("\nNothing to do.")
        return EXIT_OK

    if args.trash:
        prompt = (
            f"\nSend {n_files} duplicate(s) to the system TRASH? "
            "One copy of each group is kept. [s/N] "
        )
    else:
        prompt = (
            f"\nMove {n_files} duplicate(s) to {folder / DUPLICATES_FOLDER}? One copy of "
            "each group is kept; 'face-sorter undo' restores them. [s/N] "
        )
    if not args.yes and not _ask(prompt):
        print("Cancelled. Nothing was changed.")
        return EXIT_OK

    try:
        if args.trash:
            report = trash_duplicates(result, selected, confirm=True)
            print(report.summary())
            return EXIT_ERROR if report.failed else EXIT_OK
        plan = build_dedupe_plan(result, selected)
        applied = apply_plan(plan, confirm_move=True)
    except (DedupeError, OrganizerError) as exc:
        return _error(f"{exc}. Nothing was changed.")
    print(applied.summary())
    print(f'Undo with: face-sorter undo "{applied.manifest_path}"')
    return EXIT_OK


def _cmd_gui(args: argparse.Namespace) -> int:
    from face_sorter.gui.app import run_gui

    return run_gui()


def _cmd_undo(args: argparse.Namespace) -> int:
    from face_sorter.services.organizer import OrganizerError, undo

    try:
        report = undo(args.manifest, dry_run=args.dry_run)
    except OrganizerError as exc:
        return _error(str(exc))
    if args.dry_run:
        print("DRY RUN: nothing was changed.")
    print(report.summary())
    return EXIT_ERROR if report.errors else EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser with the ``scan``, ``gui`` and ``undo`` subcommands."""
    parser = argparse.ArgumentParser(
        prog="face-sorter",
        description="Group photos by person into folders (100% local).",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("-v", "--verbose", action="store_true", help="Show detailed logs.")
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
    scan.add_argument(
        "--plan", type=Path, help="Also save the plan as JSON to this file (for review)."
    )
    scan.add_argument(
        "--threshold",
        type=float,
        help="Clustering distance threshold (lower = stricter). Default from settings.",
    )
    scan.add_argument("--cache", type=Path, help="SQLite cache file (default: user cache dir).")
    scan.add_argument(
        "--yes", action="store_true", help="Do not ask for confirmation (needed for --mode move)."
    )
    scan.add_argument("-q", "--quiet", action="store_true", help="Hide the progress bar.")
    scan.set_defaults(func=_cmd_scan)

    dedupe = sub.add_parser(
        "dedupe", help="Find duplicate photos and move them to _duplicados/ (never deleted)."
    )
    dedupe.add_argument("folder", type=Path, help="Folder to check (recursively).")
    dedupe.add_argument(
        "--dry-run", action="store_true", help="Only list the duplicates; change nothing."
    )
    dedupe.add_argument(
        "--near",
        action="store_true",
        help="Also act on near duplicates (resized/recompressed). Review them first!",
    )
    dedupe.add_argument(
        "--max-distance", type=int, help="dHash distance for near duplicates (default 6)."
    )
    dedupe.add_argument(
        "--trash",
        action="store_true",
        help="Send duplicates to the system trash instead of moving them (asks first).",
    )
    dedupe.add_argument("--yes", action="store_true", help="Do not ask for confirmation.")
    dedupe.add_argument("--cache", type=Path, help="SQLite cache file (default: user cache dir).")
    dedupe.add_argument("-q", "--quiet", action="store_true", help="Hide the progress bar.")
    dedupe.set_defaults(func=_cmd_dedupe)

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
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )
    func: Callable[[argparse.Namespace], int] = args.func
    return func(args)


if __name__ == "__main__":
    raise SystemExit(main())

"""Command-line interface: ``face-sorter scan | dedupe | gui | undo`` (texts in Spanish)."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence
from dataclasses import replace
from pathlib import Path

from face_sorter import __version__
from face_sorter.config import (
    DUPLICATES_FOLDER,
    OUTPUT_MODE_LABELS,
    OutputMode,
    Settings,
    load_settings,
)

# argparse's own phrases, in Spanish (argparse looks them up through gettext).
_ARGPARSE_ES = {
    "usage: ": "uso: ",
    "positional arguments": "argumentos",
    "options": "opciones",
    "show this help message and exit": "muestra esta ayuda y termina",
    "show program's version number and exit": "muestra la versión y termina",
    "the following arguments are required: %s": "faltan estos argumentos: %s",
    "invalid choice: %(value)r (choose from %(choices)s)": (
        "opción no válida: %(value)r (elige entre %(choices)s)"
    ),
    "invalid %(type)s value: %(value)r": "valor %(type)s no válido: %(value)r",
    "unrecognized arguments: %s": "argumentos no reconocidos: %s",
    "%(prog)s: error: %(message)s\n": "%(prog)s: error: %(message)s\n",
    "expected one argument": "se esperaba un valor",
}
argparse._ = lambda text: _ARGPARSE_ES.get(text, text)  # type: ignore[attr-defined]

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_INTERRUPTED = 130


def _error(message: str) -> int:
    print(f"error: {message}", file=sys.stderr)
    return EXIT_ERROR


def _ask(prompt: str) -> bool:
    """Yes/no question on the terminal. Default answer is No."""
    try:
        answer = input(prompt)
    except EOFError:
        return False
    return answer.strip().lower() in {"s", "si", "sí", "y", "yes"}


def _base_settings(args: argparse.Namespace) -> Settings:
    """User settings (RF-14) with the command-line overrides applied."""
    settings = load_settings()
    if getattr(args, "cache", None) is not None:
        settings = replace(settings, cache_path=args.cache)
    return settings


def _scan_settings(args: argparse.Namespace) -> Settings:
    settings = _base_settings(args)
    if args.threshold is not None:
        settings = replace(
            settings, clustering=replace(settings.clustering, distance_threshold=args.threshold)
        )
    if args.mode is not None:
        settings = replace(settings, output_mode=OutputMode(args.mode))
    return settings


# -- scan ----------------------------------------------------------------------------------


def _cmd_scan(args: argparse.Namespace) -> int:
    source: Path = args.input.resolve()
    output: Path = args.out.resolve()
    if not source.is_dir():
        return _error(f"no existe la carpeta de fotos: {source}")
    if output == source:
        return _error("la carpeta de salida debe ser distinta de la carpeta de fotos")
    settings = _scan_settings(args)
    moving = settings.output_mode is OutputMode.MOVE and not args.dry_run
    if moving and not args.yes and not sys.stdin.isatty():
        return _error(
            "el modo mover necesita confirmación: ejecútalo en una terminal o añade --yes"
        )

    # Heavy imports (OpenCV, scikit-learn) only when actually scanning.
    from tqdm import tqdm

    from face_sorter.services.organizer import OrganizerError, apply_plan
    from face_sorter.services.pipeline import Pipeline, Progress
    from face_sorter.services.plan import build_plan
    from face_sorter.services.report import write_csv

    with tqdm(unit="foto", disable=args.quiet or None, file=sys.stderr) as bar:

        def on_progress(p: Progress) -> None:
            bar.total = p.total
            bar.update(1)

        try:
            with Pipeline(settings) as pipeline:
                result = pipeline.run(source, exclude=[output], progress=on_progress)
        except KeyboardInterrupt:
            print("\nInterrumpido. Lo analizado queda guardado; vuelve a ejecutar para continuar.")
            return EXIT_INTERRUPTED
        except FileNotFoundError as exc:  # missing models
            return _error(str(exc))
        except MemoryError:
            return _error("memoria insuficiente; prueba con una carpeta más pequeña")

    plan = build_plan(result, output, settings.output_mode)
    if args.dry_run:
        print("SIMULACIÓN (--dry-run): no se copió, movió ni modificó ningún archivo.\n")
    print(plan.summary())
    if args.plan is not None:
        plan.save(args.plan)
        print(f"\nPlan guardado en {args.plan}")
    if args.csv is not None:
        n = write_csv(plan, args.csv)
        print(f"\nReporte CSV ({n} filas) guardado en {args.csv}")
    if args.dry_run:
        return EXIT_OK

    if moving and not args.yes:
        n_sources = len({i.source for i in plan.items})
        prompt = (
            f"\nModo MOVER: {n_sources} foto(s) originales saldrán de la carpeta de fotos.\n"
            "Podrás devolverlas con 'face-sorter undo'. ¿Continuar? [s/N] "
        )
        if not _ask(prompt):
            print("Cancelado. No se cambió nada.")
            return EXIT_OK

    print()
    try:
        with tqdm(total=len(plan.items), unit="archivo", disable=args.quiet or None) as bar:
            applied = apply_plan(
                plan,
                confirm_move=moving,
                progress=lambda done, total: bar.update(done - bar.n),
            )
    except OrganizerError as exc:
        return _error(f"{exc}. No se cambió nada.")
    except KeyboardInterrupt:
        print("\nInterrumpido. Usa 'face-sorter undo' con el manifiesto de la carpeta de salida.")
        return EXIT_INTERRUPTED
    print(applied.summary())
    print(f'Para deshacer: face-sorter undo "{applied.manifest_path}"')
    return EXIT_OK


# -- dedupe --------------------------------------------------------------------------------


def _cmd_dedupe(args: argparse.Namespace) -> int:
    folder: Path = args.folder.resolve()
    if not folder.is_dir():
        return _error(f"no existe la carpeta: {folder}")
    acting = not args.dry_run
    if acting and not args.yes and not sys.stdin.isatty():
        return _error(
            "dedupe necesita confirmación: ejecútalo en una terminal, usa --dry-run o --yes"
        )

    from tqdm import tqdm

    from face_sorter.services.dedupe import (
        DedupeError,
        DedupeScanner,
        build_dedupe_plan,
        effective_selection,
        trash_duplicates,
    )
    from face_sorter.services.organizer import OrganizerError, apply_plan

    settings = _base_settings(args)
    if args.max_distance is not None:
        settings = replace(
            settings, dedupe=replace(settings.dedupe, max_distance=args.max_distance)
        )

    with tqdm(unit="foto", disable=args.quiet or None, file=sys.stderr) as bar:

        def on_progress(done: int, total: int) -> None:
            bar.total = total
            bar.update(1)

        try:
            with DedupeScanner(settings) as scanner:
                result = scanner.run(folder, progress=on_progress)
        except KeyboardInterrupt:
            print("\nInterrumpido. Las huellas calculadas quedan guardadas.")
            return EXIT_INTERRUPTED

    selected = effective_selection(result, result.default_selection(include_near=args.near))
    if args.dry_run:
        print("SIMULACIÓN (--dry-run): no se movió ni borró ningún archivo.\n")
    print(result.summary(selected))
    n_files = sum(len(result.group(g).duplicates) for g in selected)
    if not acting:
        return EXIT_OK
    if n_files == 0:
        print("\nNo hay nada que hacer.")
        return EXIT_OK

    if args.trash:
        prompt = (
            f"\n¿Enviar {n_files} duplicado(s) a la PAPELERA del sistema? "
            "De cada grupo se conserva una copia. [s/N] "
        )
    else:
        prompt = (
            f"\n¿Mover {n_files} duplicado(s) a {folder / DUPLICATES_FOLDER}? De cada grupo "
            "se conserva una copia; 'face-sorter undo' los devuelve. [s/N] "
        )
    if not args.yes and not _ask(prompt):
        print("Cancelado. No se cambió nada.")
        return EXIT_OK

    try:
        if args.trash:
            report = trash_duplicates(result, selected, confirm=True)
            print(report.summary())
            return EXIT_ERROR if report.failed else EXIT_OK
        plan = build_dedupe_plan(result, selected)
        applied = apply_plan(plan, confirm_move=True)
    except (DedupeError, OrganizerError) as exc:
        return _error(f"{exc}. No se cambió nada.")
    print(applied.summary())
    print(f'Para deshacer: face-sorter undo "{applied.manifest_path}"')
    return EXIT_OK


# -- gui / undo ----------------------------------------------------------------------------


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
        print("SIMULACIÓN (--dry-run): no se cambió nada.")
    print(report.summary())
    return EXIT_ERROR if report.errors else EXIT_OK


# -- parser --------------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser with the ``scan``, ``dedupe``, ``gui`` and ``undo`` commands."""
    parser = argparse.ArgumentParser(
        prog="face-sorter",
        description="Agrupa fotos por persona en carpetas y retira duplicados (100 % local).",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("-v", "--verbose", action="store_true", help="Muestra más detalle.")
    sub = parser.add_subparsers(dest="command", required=True, metavar="COMANDO")

    scan = sub.add_parser("scan", help="Agrupa por persona las fotos de una carpeta.")
    scan.add_argument("input", type=Path, help="Carpeta de fotos (se recorre entera).")
    scan.add_argument("--out", type=Path, required=True, help="Carpeta de salida.")
    modes = ", ".join(f"{m.value} = {OUTPUT_MODE_LABELS[m]}" for m in OutputMode)
    scan.add_argument(
        "--mode",
        choices=[m.value for m in OutputMode],
        help=f"Modo ({modes}). Por defecto, el de tus ajustes (copy). 'move' pide confirmación.",
    )
    scan.add_argument(
        "--dry-run", action="store_true", help="Muestra qué se haría sin tocar ningún archivo."
    )
    scan.add_argument("--plan", type=Path, help="Guarda también el plan completo en JSON.")
    scan.add_argument(
        "--csv", type=Path, help="Guarda un reporte CSV (foto; grupo; destino; rostros; estado)."
    )
    scan.add_argument(
        "--threshold",
        type=float,
        help="Umbral de agrupación (más bajo = más estricto). Por defecto, el de tus ajustes.",
    )
    scan.add_argument("--cache", type=Path, help="Archivo de caché SQLite (opcional).")
    scan.add_argument("--yes", action="store_true", help="No pedir confirmación.")
    scan.add_argument("-q", "--quiet", action="store_true", help="Oculta la barra de progreso.")
    scan.set_defaults(func=_cmd_scan)

    dedupe = sub.add_parser(
        "dedupe", help="Busca fotos duplicadas y las mueve a _duplicados/ (nunca las borra)."
    )
    dedupe.add_argument("folder", type=Path, help="Carpeta a revisar (se recorre entera).")
    dedupe.add_argument(
        "--dry-run", action="store_true", help="Solo lista los duplicados; no cambia nada."
    )
    dedupe.add_argument(
        "--near",
        action="store_true",
        help="Incluye los casi duplicados (redimensionados, recomprimidos). ¡Revísalos antes!",
    )
    dedupe.add_argument(
        "--max-distance",
        type=int,
        help="Sensibilidad de los casi duplicados (por defecto 6; menos = más estricto).",
    )
    dedupe.add_argument(
        "--trash",
        action="store_true",
        help="Envía los duplicados a la papelera del sistema en vez de moverlos (pregunta antes).",
    )
    dedupe.add_argument("--yes", action="store_true", help="No pedir confirmación.")
    dedupe.add_argument("--cache", type=Path, help="Archivo de caché SQLite (opcional).")
    dedupe.add_argument("-q", "--quiet", action="store_true", help="Oculta la barra de progreso.")
    dedupe.set_defaults(func=_cmd_dedupe)

    gui = sub.add_parser("gui", help="Abre la interfaz gráfica.")
    gui.set_defaults(func=_cmd_gui)

    undo = sub.add_parser("undo", help="Deshace lo registrado en un manifiesto.")
    undo.add_argument("manifest", type=Path, help="Archivo manifest_*.json.")
    undo.add_argument("--dry-run", action="store_true", help="Muestra qué se desharía sin hacerlo.")
    undo.set_defaults(func=_cmd_undo)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for the ``face-sorter`` command."""
    from face_sorter.logging_setup import setup_logging

    for stream in (sys.stdout, sys.stderr):
        # Never crash on a character the console/pipe cannot encode (e.g. cp1252).
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    args = build_parser().parse_args(argv)
    setup_logging(verbose=args.verbose)
    func: Callable[[argparse.Namespace], int] = args.func
    return func(args)


if __name__ == "__main__":
    raise SystemExit(main())

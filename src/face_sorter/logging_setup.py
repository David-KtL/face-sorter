"""Logging: warnings to the terminal, full detail to a rotating log file (RNF-07)."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from face_sorter.config import log_path

LOG_MAX_BYTES = 1_000_000
LOG_BACKUPS = 3
_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def setup_logging(verbose: bool = False, file: Path | None = None) -> Path | None:
    """Configure the root logger. Returns the log file path (None if it can't be written).

    The console shows warnings (or info with ``verbose``); the file always gets info and
    above, so problems can be diagnosed after the fact.
    """
    root = logging.getLogger()
    for handler in list(root.handlers):
        if getattr(handler, "_face_sorter", False):
            root.removeHandler(handler)
            handler.close()
    root.setLevel(logging.INFO)

    console = logging.StreamHandler()
    console.setLevel(logging.INFO if verbose else logging.WARNING)
    console.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    console._face_sorter = True  # type: ignore[attr-defined]
    root.addHandler(console)

    path = file or log_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            path, maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUPS, encoding="utf-8"
        )
    except OSError:
        logging.getLogger(__name__).warning("Cannot write the log file %s", path)
        return None
    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter(_FORMAT))
    handler._face_sorter = True  # type: ignore[attr-defined]
    root.addHandler(handler)
    return path

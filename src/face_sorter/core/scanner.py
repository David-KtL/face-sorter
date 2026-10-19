"""Recursive discovery of supported image files (RF-01)."""

from __future__ import annotations

import logging
import os
from collections.abc import Iterable, Iterator
from pathlib import Path

from face_sorter.config import RESERVED_DIR_NAMES, SUPPORTED_EXTENSIONS

log = logging.getLogger(__name__)


def is_supported(path: Path, extensions: Iterable[str] = SUPPORTED_EXTENSIONS) -> bool:
    """Return True if ``path`` has a supported image extension (case-insensitive)."""
    return path.suffix.lower() in set(extensions)


def scan(
    root: Path,
    *,
    exclude: Iterable[Path] = (),
    extensions: Iterable[str] = SUPPORTED_EXTENSIONS,
) -> Iterator[Path]:
    """Yield every supported image under ``root``, recursively and in a stable order.

    Hidden files and folders (starting with ``.``) and reserved folders such as
    ``_duplicados`` are skipped, symlinked folders are
    not followed (avoids loops), and any folder in ``exclude`` (for example the output
    folder, if it lives inside ``root``) is pruned.

    Raises:
        NotADirectoryError: if ``root`` is not an existing directory.
    """
    root = Path(root)
    if not root.is_dir():
        raise NotADirectoryError(f"Not a folder: {root}")

    exts = {e.lower() for e in extensions}
    excluded = {Path(p).resolve() for p in exclude}

    def on_error(err: OSError) -> None:
        log.warning("Cannot read folder %s: %s", err.filename, err.strerror)

    for dirpath, dirnames, filenames in os.walk(root, onerror=on_error, followlinks=False):
        current = Path(dirpath)
        dirnames[:] = sorted(
            d
            for d in dirnames
            if not d.startswith(".")
            and d not in RESERVED_DIR_NAMES
            and (current / d).resolve() not in excluded
        )
        for name in sorted(filenames):
            if name.startswith("."):
                continue
            path = current / name
            if path.suffix.lower() in exts and path.is_file():
                yield path

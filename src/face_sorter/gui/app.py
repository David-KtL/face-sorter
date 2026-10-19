"""GUI entry point (``face-sorter gui``)."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from types import TracebackType

from face_sorter.config import Settings
from face_sorter.logging_setup import setup_logging

log = logging.getLogger(__name__)


def install_excepthook(log_file: Path | None) -> None:
    """Show unexpected errors in a dialog (and log them) instead of closing silently."""
    from PySide6.QtWidgets import QApplication, QMessageBox

    from face_sorter.gui import strings as S

    def hook(kind: type[BaseException], exc: BaseException, tb: TracebackType | None) -> None:
        log.critical("Unexpected error", exc_info=(kind, exc, tb))
        if QApplication.instance() is not None:
            QMessageBox.critical(
                None,
                S.UNEXPECTED_ERROR,
                S.UNEXPECTED_ERROR_TEXT.format(error=exc, log=log_file or "-"),
            )

    sys.excepthook = hook


def run_gui(settings: Settings | None = None) -> int:
    """Open the main window and run the Qt event loop. Returns the exit code."""
    from PySide6.QtWidgets import QApplication

    from face_sorter.gui.main_window import MainWindow

    install_excepthook(setup_logging())
    app = QApplication.instance() or QApplication(sys.argv)
    window = MainWindow(settings)
    window.show()
    return int(app.exec())

"""GUI entry point (``face-sorter gui``)."""

from __future__ import annotations

import sys

from face_sorter.config import Settings


def run_gui(settings: Settings | None = None) -> int:
    """Open the main window and run the Qt event loop. Returns the exit code."""
    from PySide6.QtWidgets import QApplication

    from face_sorter.gui.main_window import MainWindow

    app = QApplication.instance() or QApplication(sys.argv)
    window = MainWindow(settings)
    window.show()
    return int(app.exec())

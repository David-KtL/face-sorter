"""Background workers: heavy work never runs in the GUI thread (RNF-03).

Each worker is a QObject moved to its own QThread. Results and progress come back
through signals (queued to the GUI thread automatically). Cancellation uses a
thread-safe event checked between images/files.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Qt, QThread, Signal, Slot

from face_sorter.config import Settings
from face_sorter.services.dedupe import DedupeResult, DedupeScanner, trash_duplicates
from face_sorter.services.organizer import apply_plan, undo
from face_sorter.services.pipeline import Pipeline, ScanCancelled
from face_sorter.services.plan import OrganizationPlan

log = logging.getLogger(__name__)

PipelineFactory = Callable[[Settings], Pipeline]


class Worker(QObject):
    """Base worker: subclasses implement :meth:`work`."""

    progress = Signal(int, int)
    finished = Signal(object)
    failed = Signal(str)
    cancelled = Signal()
    done = Signal()  # always emitted last (used to stop the thread)

    def __init__(self) -> None:
        super().__init__()
        self._cancel = threading.Event()
        self.thread_id: int | None = None  # for tests: proves work ran off the GUI thread

    def cancel(self) -> None:
        """Ask the worker to stop at the next safe point."""
        self._cancel.set()

    @property
    def is_cancelled(self) -> bool:
        """True once :meth:`cancel` was called."""
        return self._cancel.is_set()

    def work(self) -> Any:  # pragma: no cover - abstract
        raise NotImplementedError

    @Slot()
    def run(self) -> None:
        """Entry point executed in the worker thread."""
        self.thread_id = threading.get_ident()
        try:
            result = self.work()
        except ScanCancelled:
            self.cancelled.emit()
        except Exception as exc:  # noqa: BLE001 - reported to the user, never crash the GUI
            log.exception("Background task failed")
            self.failed.emit(str(exc))
        else:
            if self.is_cancelled and result is None:
                self.cancelled.emit()
            else:
                self.finished.emit(result)
        finally:
            self.done.emit()


class ScanWorker(Worker):
    """Runs the analysis pipeline."""

    def __init__(
        self, settings: Settings, source: Path, output: Path, factory: PipelineFactory
    ) -> None:
        super().__init__()
        self.settings, self.source, self.output, self.factory = settings, source, output, factory

    def work(self) -> Any:
        with self.factory(self.settings) as pipeline:
            return pipeline.run(
                self.source,
                exclude=[self.output],
                progress=lambda p: self.progress.emit(p.done, p.total),
                cancel=self._cancel.is_set,
            )


class ApplyWorker(Worker):
    """Applies a plan (copy/link/move) with a manifest."""

    def __init__(self, plan: OrganizationPlan, confirm_move: bool) -> None:
        super().__init__()
        self.plan, self.confirm_move = plan, confirm_move

    def work(self) -> Any:
        return apply_plan(
            self.plan,
            confirm_move=self.confirm_move,
            progress=lambda d, t: self.progress.emit(d, t),
            cancel=self._cancel.is_set,
        )


class UndoWorker(Worker):
    """Reverts a manifest (or previews it with ``dry_run``)."""

    def __init__(self, manifest: Path, dry_run: bool = False) -> None:
        super().__init__()
        self.manifest, self.dry_run = manifest, dry_run

    def work(self) -> Any:
        return undo(self.manifest, dry_run=self.dry_run)


class DedupeWorker(Worker):
    """Finds duplicate groups (hashes are cached)."""

    def __init__(self, settings: Settings, folder: Path) -> None:
        super().__init__()
        self.settings, self.folder = settings, folder

    def work(self) -> Any:
        with DedupeScanner(self.settings) as scanner:
            return scanner.run(
                self.folder,
                progress=lambda d, t: self.progress.emit(d, t),
                cancel=self._cancel.is_set,
            )


class TrashWorker(Worker):
    """Sends the duplicates of the selected groups to the system trash."""

    def __init__(self, result: DedupeResult, selected: list[str]) -> None:
        super().__init__()
        self.result, self.selected = result, selected

    def work(self) -> Any:
        return trash_duplicates(self.result, self.selected, confirm=True)


def start(worker: Worker) -> QThread:
    """Run ``worker`` in a new QThread. The thread stops by itself when the work is done.

    Keep a reference to both the worker and the returned thread until it finishes.
    """
    thread = QThread()
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    # Direct: quit() is thread-safe, and a queued call would deadlock if the GUI thread
    # is blocked in thread.wait() (e.g. closing the window during a scan).
    worker.done.connect(thread.quit, Qt.ConnectionType.DirectConnection)
    thread.start()
    return thread

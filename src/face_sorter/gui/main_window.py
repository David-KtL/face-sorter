"""Main window: setup -> scan (background) -> review -> apply (background) -> result/undo."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt, QThread, QUrl
from PySide6.QtGui import QAction, QCloseEvent, QDesktopServices, QIcon, QImage, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from face_sorter.config import OutputMode, Settings
from face_sorter.core.clustering import UNCLASSIFIED
from face_sorter.gui import strings as S
from face_sorter.gui.thumbnails import THUMB_SIZE, ThumbnailLoader
from face_sorter.gui.workers import (
    ApplyWorker,
    PipelineFactory,
    ScanWorker,
    UndoWorker,
    Worker,
    start,
)
from face_sorter.services.organizer import ApplyResult, UndoReport
from face_sorter.services.pipeline import FaceInfo, Pipeline, ScanResult
from face_sorter.services.plan import FaceKey, OrganizationPlan
from face_sorter.services.review import ReviewError, ReviewSession, face_key

ROLE = Qt.ItemDataRole.UserRole
ICON_ROLE = Qt.ItemDataRole.UserRole + 1  # thumbnail key of the item

# Left-list entries: ("person", label) or one of these special views.
VIEW_UNCLASSIFIED = "unclassified"
VIEW_LOW_QUALITY = "low_quality"
VIEW_EXCLUDED = "excluded"
VIEW_NO_FACE = "no_face"

MODES = [
    (OutputMode.COPY, S.MODE_COPY),
    (OutputMode.HARDLINK, S.MODE_HARDLINK),
    (OutputMode.MOVE, S.MODE_MOVE),
]


class Dialogs:
    """Modal dialogs, isolated so tests can replace them."""

    def __init__(self, parent: QWidget) -> None:
        self.parent = parent

    def ask(self, title: str, text: str) -> bool:
        answer = QMessageBox.question(
            self.parent, title, text, defaultButton=QMessageBox.StandardButton.No
        )
        return answer == QMessageBox.StandardButton.Yes

    def info(self, title: str, text: str) -> None:
        QMessageBox.information(self.parent, title, text)

    def error(self, title: str, text: str) -> None:
        QMessageBox.critical(self.parent, title, text)

    def text(self, title: str, label: str, default: str) -> str | None:
        value, ok = QInputDialog.getText(self.parent, title, label, text=default)
        return value if ok else None

    def choose(self, title: str, label: str, items: list[str]) -> str | None:
        value, ok = QInputDialog.getItem(self.parent, title, label, items, 0, False)
        return value if ok else None

    def folder(self, title: str, start: str) -> str | None:
        return QFileDialog.getExistingDirectory(self.parent, title, start) or None

    def open_file(self, title: str, start: str, filters: str) -> str | None:
        return QFileDialog.getOpenFileName(self.parent, title, start, filters)[0] or None

    def show_text(self, title: str, text: str) -> None:
        box = QMessageBox(self.parent)
        box.setWindowTitle(title)
        box.setText(title)
        box.setDetailedText(text)
        box.setInformativeText(text.split("\n\n")[0])
        box.exec()


class MainWindow(QMainWindow):
    """The application window."""

    def __init__(
        self,
        settings: Settings | None = None,
        pipeline_factory: PipelineFactory = Pipeline,
    ) -> None:
        super().__init__()
        self.settings = settings or Settings()
        self.pipeline_factory = pipeline_factory
        self.dialogs = Dialogs(self)
        self.session: ReviewSession | None = None
        self.last_apply: ApplyResult | None = None
        self._undo_manifest = Path()
        self.worker: Worker | None = None
        self.task_thread: QThread | None = None
        self._thumbs: dict[object, QIcon] = {}
        self._placeholder_icon: QIcon | None = None
        self.loader = ThumbnailLoader(self)
        self.loader.ready.connect(self._on_thumbnail)

        self.setWindowTitle(S.APP_TITLE)
        self.resize(1100, 720)
        self.pages = QStackedWidget()
        self.setCentralWidget(self.pages)
        self._build_setup_page()
        self._build_review_page()
        self._build_result_page()
        self._build_menu()
        self.pages.setCurrentWidget(self.setup_page)

    # =================================================================== building UI

    def _build_menu(self) -> None:
        menu = self.menuBar().addMenu(S.MENU_FILE)
        undo_action = QAction(S.MENU_UNDO_MANIFEST, self)
        undo_action.triggered.connect(self.undo_from_file)
        menu.addAction(undo_action)
        quit_action = QAction(S.MENU_QUIT, self)
        quit_action.triggered.connect(self.close)
        menu.addAction(quit_action)

    def _folder_row(self, edit: QLineEdit, title: str) -> QWidget:
        row = QWidget()
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 0, 0, 0)
        button = QPushButton(S.BROWSE)
        button.clicked.connect(lambda: self._browse(edit, title))
        lay.addWidget(edit)
        lay.addWidget(button)
        return row

    def _build_setup_page(self) -> None:
        self.setup_page = QWidget()
        layout = QVBoxLayout(self.setup_page)
        form = QFormLayout()
        self.source_edit = QLineEdit()
        self.output_edit = QLineEdit()
        self.mode_combo = QComboBox()
        for mode, label in MODES:
            self.mode_combo.addItem(label, mode)
        form.addRow(S.SOURCE_LABEL, self._folder_row(self.source_edit, S.CHOOSE_SOURCE))
        form.addRow(S.OUTPUT_LABEL, self._folder_row(self.output_edit, S.CHOOSE_OUTPUT))
        form.addRow(S.MODE_LABEL, self.mode_combo)
        layout.addLayout(form)

        hint = QLabel(S.SETUP_HINT)
        hint.setWordWrap(True)
        layout.addWidget(hint)

        buttons = QHBoxLayout()
        self.scan_button = QPushButton(S.SCAN)
        self.scan_button.clicked.connect(self.start_scan)
        self.cancel_button = QPushButton(S.CANCEL)
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel_work)
        buttons.addWidget(self.scan_button)
        buttons.addWidget(self.cancel_button)
        buttons.addStretch()
        layout.addLayout(buttons)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.status = QLabel()
        layout.addWidget(self.progress)
        layout.addWidget(self.status)
        layout.addStretch()
        self.pages.addWidget(self.setup_page)

    def _build_review_page(self) -> None:
        self.review_page = QWidget()
        layout = QVBoxLayout(self.review_page)
        hint = QLabel(S.REVIEW_HINT)
        hint.setWordWrap(True)
        layout.addWidget(hint)

        splitter = QSplitter()
        left = QWidget()
        left_lay = QVBoxLayout(left)
        left_lay.addWidget(QLabel(S.GROUPS))
        self.group_list = QListWidget()
        self.group_list.setIconSize(QSize(48, 48))
        self.group_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.group_list.itemSelectionChanged.connect(self._on_group_selected)
        left_lay.addWidget(self.group_list)
        group_buttons = QHBoxLayout()
        self.rename_button = QPushButton(S.RENAME)
        self.rename_button.clicked.connect(self.rename_group)
        self.merge_button = QPushButton(S.MERGE)
        self.merge_button.clicked.connect(self.merge_groups)
        group_buttons.addWidget(self.rename_button)
        group_buttons.addWidget(self.merge_button)
        left_lay.addLayout(group_buttons)
        splitter.addWidget(left)

        right = QWidget()
        right_lay = QVBoxLayout(right)
        self.view_title = QLabel()
        right_lay.addWidget(self.view_title)
        self.face_list = QListWidget()
        self.face_list.setViewMode(QListWidget.ViewMode.IconMode)
        self.face_list.setIconSize(QSize(THUMB_SIZE, THUMB_SIZE))
        self.face_list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.face_list.setMovement(QListWidget.Movement.Static)
        self.face_list.setSpacing(4)
        self.face_list.setUniformItemSizes(True)
        self.face_list.setGridSize(QSize(THUMB_SIZE + 12, THUMB_SIZE + 24))
        self.face_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.face_list.itemSelectionChanged.connect(self._update_buttons)
        right_lay.addWidget(self.face_list)
        face_buttons = QHBoxLayout()
        self.split_button = QPushButton(S.SPLIT)
        self.split_button.clicked.connect(self.split_faces)
        self.move_button = QPushButton(S.MOVE_TO)
        self.move_button.clicked.connect(self.move_faces)
        self.exclude_face_button = QPushButton(S.EXCLUDE_FACES)
        self.exclude_face_button.clicked.connect(self.exclude_faces)
        self.exclude_photo_button = QPushButton(S.EXCLUDE_PHOTOS)
        self.exclude_photo_button.clicked.connect(self.exclude_photos)
        self.restore_button = QPushButton(S.RESTORE)
        self.restore_button.clicked.connect(self.restore_faces)
        for b in (
            self.split_button,
            self.move_button,
            self.exclude_face_button,
            self.exclude_photo_button,
            self.restore_button,
        ):
            face_buttons.addWidget(b)
        face_buttons.addStretch()
        right_lay.addLayout(face_buttons)
        splitter.addWidget(right)
        splitter.setSizes([320, 780])
        layout.addWidget(splitter, 1)

        bottom = QHBoxLayout()
        back = QPushButton(S.BACK)
        back.clicked.connect(lambda: self.pages.setCurrentWidget(self.setup_page))
        self.preview_button = QPushButton(S.PREVIEW)
        self.preview_button.clicked.connect(self.preview)
        self.apply_button = QPushButton(S.APPLY)
        self.apply_button.clicked.connect(self.start_apply)
        bottom.addWidget(back)
        bottom.addStretch()
        bottom.addWidget(self.preview_button)
        bottom.addWidget(self.apply_button)
        layout.addLayout(bottom)

        self.apply_progress = QProgressBar()
        self.apply_progress.setVisible(False)
        layout.addWidget(self.apply_progress)
        self.pages.addWidget(self.review_page)

    def _build_result_page(self) -> None:
        self.result_page = QWidget()
        layout = QVBoxLayout(self.result_page)
        layout.addWidget(QLabel(S.RESULT_TITLE))
        self.result_text = QPlainTextEdit()
        self.result_text.setReadOnly(True)
        layout.addWidget(self.result_text)
        buttons = QHBoxLayout()
        self.open_output_button = QPushButton(S.OPEN_OUTPUT)
        self.open_output_button.clicked.connect(self._open_output)
        self.undo_button = QPushButton(S.UNDO)
        self.undo_button.clicked.connect(self.undo_last)
        new_scan = QPushButton(S.NEW_SCAN)
        new_scan.clicked.connect(lambda: self.pages.setCurrentWidget(self.setup_page))
        buttons.addWidget(self.open_output_button)
        buttons.addWidget(self.undo_button)
        buttons.addStretch()
        buttons.addWidget(new_scan)
        layout.addLayout(buttons)
        self.pages.addWidget(self.result_page)

    # ===================================================================== helpers

    def _browse(self, edit: QLineEdit, title: str) -> None:
        chosen = self.dialogs.folder(title, edit.text())
        if chosen:
            edit.setText(chosen)

    @property
    def busy(self) -> bool:
        """True while a background task is running."""
        return self.task_thread is not None and self.task_thread.isRunning()

    def _run(self, worker: Worker) -> None:
        # Connect worker signals only to methods of this window, never to lambdas: in
        # PySide6 a lambda runs in the *emitting* (worker) thread, not the GUI thread.
        self.worker = worker
        self.task_thread = start(worker)

    def cancel_work(self) -> None:
        """Ask the running background task to stop."""
        if self.worker is not None:
            self.worker.cancel()

    def _selected_mode(self) -> OutputMode:
        return OutputMode(self.mode_combo.currentData())

    # ======================================================================= scan

    def start_scan(self) -> None:
        """Validate the folders and start scanning in the background."""
        if self.busy:
            return
        src_text, out_text = self.source_edit.text().strip(), self.output_edit.text().strip()
        if not src_text or not out_text:
            self.dialogs.error(S.APP_TITLE, S.NEED_FOLDERS)
            return
        source, output = Path(src_text).resolve(), Path(out_text).resolve()
        if not source.is_dir():
            self.dialogs.error(S.APP_TITLE, S.SOURCE_MISSING)
            return
        if source == output:
            self.dialogs.error(S.APP_TITLE, S.SAME_FOLDERS)
            return

        worker = ScanWorker(self.settings, source, output, self.pipeline_factory)
        worker.progress.connect(self._on_scan_progress)
        worker.finished.connect(self._on_scan_finished)
        worker.failed.connect(self._on_scan_failed)
        worker.cancelled.connect(self._on_scan_cancelled)
        self.scan_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)
        self.status.setText(S.SCAN_STARTING)
        self._run(worker)

    def _on_scan_progress(self, done: int, total: int) -> None:
        self.progress.setRange(0, total)
        self.progress.setValue(done)
        self.status.setText(S.SCANNING.format(done=done, total=total))

    def _reset_setup(self) -> None:
        self.scan_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.progress.setVisible(False)

    def _on_scan_failed(self, detail: str) -> None:
        self._on_scan_ended(S.SCAN_FAILED, detail)

    def _on_scan_cancelled(self) -> None:
        self._on_scan_ended(S.SCAN_CANCELLED, None)

    def _on_scan_ended(self, message: str, detail: str | None) -> None:
        self._reset_setup()
        self.status.setText(message)
        if detail:
            self.dialogs.error(message, detail)

    def _on_scan_finished(self, result: ScanResult) -> None:
        self._reset_setup()
        self.status.setText("")
        self.load_result(result)

    def load_result(self, result: ScanResult) -> None:
        """Show a scan result for review."""
        self.session = ReviewSession(result)
        self._thumbs.clear()
        self.refresh_groups()
        self.pages.setCurrentWidget(self.review_page)
        if self.group_list.count():
            self.group_list.setCurrentRow(0)

    # ===================================================================== review

    def refresh_groups(self, keep: object | None = None) -> None:
        """Redraw the group list, keeping the selection on ``keep`` if possible."""
        s = self.session
        if s is None:
            return
        current = keep if keep is not None else self._current_view()
        self.group_list.blockSignals(True)
        self.group_list.clear()
        for g in s.groups():
            item = QListWidgetItem(
                S.PERSON_ITEM.format(name=g.name, faces=len(g.faces), images=g.n_images)
            )
            item.setData(ROLE, ("person", g.label))
            first = g.faces[0]
            item.setData(ICON_ROLE, face_key(first))
            item.setIcon(self._icon(face_key(first), first))
            self.group_list.addItem(item)
        specials = [
            (VIEW_UNCLASSIFIED, S.UNCLASSIFIED_ITEM, len(s.unclassified_faces())),
            (VIEW_LOW_QUALITY, S.LOW_QUALITY_ITEM, len(s.low_quality_faces())),
            (VIEW_EXCLUDED, S.EXCLUDED_ITEM, len(s.excluded_face_list())),
            (VIEW_NO_FACE, S.NO_FACE_ITEM, len(s.no_face_images())),
        ]
        for view, text, n in specials:
            if n:
                item = QListWidgetItem(text.format(n=n))
                item.setData(ROLE, (view, None))
                self.group_list.addItem(item)
        self.group_list.blockSignals(False)

        row = next(
            (
                i
                for i in range(self.group_list.count())
                if self.group_list.item(i).data(ROLE) == current
            ),
            0 if self.group_list.count() else -1,
        )
        self.group_list.setCurrentRow(row)
        self._on_group_selected()

    def _current_view(self) -> tuple[str, int | None] | None:
        item = self.group_list.currentItem()
        return None if item is None else item.data(ROLE)

    def _selected_labels(self) -> list[int]:
        return [
            item.data(ROLE)[1]
            for item in self.group_list.selectedItems()
            if item.data(ROLE)[0] == "person"
        ]

    def _view_faces(self, view: tuple[str, int | None]) -> list[FaceInfo]:
        s = self.session
        assert s is not None
        kind, label = view
        if kind == "person":
            return next((list(g.faces) for g in s.groups() if g.label == label), [])
        return {
            VIEW_UNCLASSIFIED: s.unclassified_faces,
            VIEW_LOW_QUALITY: s.low_quality_faces,
            VIEW_EXCLUDED: s.excluded_face_list,
        }.get(kind, list)()

    def _on_group_selected(self) -> None:
        self.face_list.clear()
        view = self._current_view()
        if view is None or self.session is None:
            self.view_title.setText("")
            self._update_buttons()
            return
        self.view_title.setText(self.group_list.currentItem().text())
        if view[0] == VIEW_NO_FACE:
            for path in self.session.no_face_images():
                item = QListWidgetItem(self._icon(("photo", path), None, path), path.name)
                item.setToolTip(str(path))
                item.setData(ROLE, ("photo", path))
                item.setData(ICON_ROLE, ("photo", path))
                self.face_list.addItem(item)
        else:
            for face in self._view_faces(view):
                k = face_key(face)
                item = QListWidgetItem(self._icon(k, face), "")
                item.setToolTip(f"{face.image}\n{', '.join(face.quality.issues) or ''}".strip())
                item.setData(ROLE, k)
                item.setData(ICON_ROLE, k)
                self.face_list.addItem(item)
        self._update_buttons()

    def _placeholder(self) -> QIcon:
        if self._placeholder_icon is None:
            pixmap = QPixmap(THUMB_SIZE, THUMB_SIZE)
            pixmap.fill(Qt.GlobalColor.lightGray)
            self._placeholder_icon = QIcon(pixmap)
        return self._placeholder_icon

    def _icon(self, key: object, face: FaceInfo | None, path: Path | None = None) -> QIcon:
        """Thumbnail icon for ``key``; a grey placeholder until it is loaded."""
        if key not in self._thumbs:
            self._thumbs[key] = self._placeholder()
            if face is not None:
                self.loader.request([(key, face.image, face.face.bbox)])
            elif path is not None:
                self.loader.request([(key, path, None)])
        return self._thumbs[key]

    def _on_thumbnail(self, key: object, image: QImage) -> None:
        icon = QIcon(QPixmap.fromImage(image))
        self._thumbs[key] = icon
        for lst in (self.face_list, self.group_list):
            for i in range(lst.count()):
                item = lst.item(i)
                if item.data(ICON_ROLE) == key:
                    item.setIcon(icon)

    def _selected_faces(self) -> list[FaceKey]:
        return [
            item.data(ROLE)
            for item in self.face_list.selectedItems()
            if item.data(ROLE)[0] != "photo"
        ]

    def _update_buttons(self) -> None:
        view = self._current_view()
        kind = view[0] if view else None
        has_faces = bool(self._selected_faces())
        groupable = kind in ("person", VIEW_UNCLASSIFIED)
        self.rename_button.setEnabled(kind == "person")
        self.merge_button.setEnabled(len(self._selected_labels()) >= 2)
        self.split_button.setEnabled(has_faces and groupable)
        self.move_button.setEnabled(has_faces and groupable)
        self.exclude_face_button.setEnabled(has_faces and kind != VIEW_EXCLUDED)
        self.exclude_photo_button.setEnabled(
            kind != VIEW_EXCLUDED and bool(self.face_list.selectedItems())
        )
        self.restore_button.setEnabled(has_faces and kind == VIEW_EXCLUDED)
        idle = not self.busy
        self.apply_button.setEnabled(idle and self.session is not None)
        self.preview_button.setEnabled(self.session is not None)

    def _edit(self, action: object, keep: object | None = None) -> None:
        """Run a review edit, report rejections, and redraw."""
        try:
            if callable(action):
                keep = action() or keep
        except ReviewError as exc:
            self.dialogs.error(S.EDIT_ERROR, str(exc))
            return
        self.refresh_groups(keep)

    def rename_group(self) -> None:
        """Rename the current person group."""
        view, s = self._current_view(), self.session
        if not view or view[0] != "person" or s is None or view[1] is None:
            return
        label = view[1]
        new = self.dialogs.text(S.RENAME_TITLE, S.RENAME_PROMPT, s.name_of(label))
        if new is None:
            return

        def do() -> None:
            used = s.rename(label, new)
            if used != new.strip():
                self.dialogs.info(S.RENAME_TITLE, S.RENAMED_SANITIZED.format(name=used))

        self._edit(do, view)

    def merge_groups(self) -> None:
        """Merge the selected person groups into the largest one."""
        labels, s = self._selected_labels(), self.session
        if s is None or len(labels) < 2:
            self.dialogs.error(S.EDIT_ERROR, S.MERGE_NEED_TWO)
            return
        sizes = {g.label: len(g.faces) for g in s.groups()}
        target = max(labels, key=lambda lb: (sizes.get(lb, 0), -lb))
        self._edit(lambda: s.merge(target, labels), ("person", target))

    def split_faces(self) -> None:
        """Move the selected faces to a new group and show it."""
        keys, s = self._selected_faces(), self.session
        if s is None:
            return
        if not keys:
            self.dialogs.error(S.EDIT_ERROR, S.SELECT_FACES)
            return
        self._edit(lambda: ("person", s.split(keys)))

    def move_faces(self) -> None:
        """Move the selected faces to another group (or to unclassified)."""
        keys, s = self._selected_faces(), self.session
        if s is None or not keys:
            return
        groups = s.groups()
        options = [g.name for g in groups] + [S.UNCLASSIFIED_TARGET]
        choice = self.dialogs.choose(S.MOVE_TITLE, S.MOVE_PROMPT, options)
        if choice is None:
            return
        label = next((g.label for g in groups if g.name == choice), UNCLASSIFIED)
        self._edit(lambda: s.assign(keys, label))

    def exclude_faces(self) -> None:
        """Exclude the selected faces."""
        keys, s = self._selected_faces(), self.session
        if s is not None and keys:
            self._edit(lambda: s.exclude_faces(keys))

    def exclude_photos(self) -> None:
        """Exclude the photos of the selected faces (they will not be copied)."""
        s = self.session
        if s is None:
            return
        paths = {
            data[1] if data[0] == "photo" else data[0]
            for data in (item.data(ROLE) for item in self.face_list.selectedItems())
        }
        if paths:
            self._edit(lambda: s.exclude_images(paths))

    def restore_faces(self) -> None:
        """Bring excluded faces (and their photos) back."""
        keys, s = self._selected_faces(), self.session
        if s is not None and keys:
            self._edit(lambda: s.include_faces(keys))

    def current_plan(self) -> OrganizationPlan:
        """The organization plan for the reviewed state."""
        assert self.session is not None
        output = Path(self.output_edit.text().strip()).resolve()
        return self.session.plan(output, self._selected_mode())

    def preview(self) -> None:
        """Show the dry-run summary."""
        if self.session is None:
            return
        try:
            plan = self.current_plan()
        except ValueError as exc:
            self.dialogs.error(S.EDIT_ERROR, str(exc))
            return
        self.dialogs.show_text(S.PREVIEW_TITLE, plan.summary())

    # ====================================================================== apply

    def start_apply(self) -> None:
        """Apply the reviewed plan in the background (asks first when moving)."""
        if self.session is None or self.busy:
            return
        try:
            plan = self.current_plan()
        except ValueError as exc:
            self.dialogs.error(S.EDIT_ERROR, str(exc))
            return
        moving = plan.mode is OutputMode.MOVE
        if moving:
            n = len({i.source for i in plan.items})
            if not self.dialogs.ask(S.CONFIRM_MOVE_TITLE, S.CONFIRM_MOVE.format(n=n)):
                return
        worker = ApplyWorker(plan, confirm_move=moving)
        worker.progress.connect(self._on_apply_progress)
        worker.finished.connect(self._on_apply_finished)
        worker.failed.connect(self._on_apply_failed)
        self.apply_button.setEnabled(False)
        self.apply_progress.setVisible(True)
        self.apply_progress.setRange(0, max(1, len(plan.items)))
        self._run(worker)

    def _on_apply_progress(self, done: int, total: int) -> None:
        self.apply_progress.setRange(0, total)
        self.apply_progress.setValue(done)

    def _on_apply_failed(self, message: str) -> None:
        self.apply_progress.setVisible(False)
        self.apply_button.setEnabled(True)
        self.dialogs.error(S.APPLY_FAILED, message)

    def _on_apply_finished(self, result: ApplyResult) -> None:
        self.apply_progress.setVisible(False)
        self.apply_button.setEnabled(True)
        self.last_apply = result
        self.result_text.setPlainText(result.summary())
        self.undo_button.setEnabled(True)
        self.pages.setCurrentWidget(self.result_page)

    def _open_output(self) -> None:
        if self.last_apply is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.last_apply.manifest.output_root))

    # ======================================================================= undo

    def undo_last(self) -> None:
        """Undo the last apply of this session."""
        if self.last_apply is not None:
            self.start_undo(self.last_apply.manifest_path)

    def undo_from_file(self) -> None:
        """Pick a manifest file and undo it."""
        chosen = self.dialogs.open_file(
            S.CHOOSE_MANIFEST, self.output_edit.text(), S.MANIFEST_FILTER
        )
        if chosen:
            self.start_undo(Path(chosen))

    def start_undo(self, manifest: Path) -> None:
        """Preview the undo, confirm, then run it in the background."""
        if self.busy:
            return
        self._undo_manifest = manifest
        preview = UndoWorker(manifest, dry_run=True)
        preview.finished.connect(self._confirm_undo)
        preview.failed.connect(self._on_undo_failed)
        self._run(preview)

    def _on_undo_failed(self, message: str) -> None:
        self.dialogs.error(S.UNDO_FAILED, message)

    def _confirm_undo(self, report: UndoReport) -> None:
        manifest = self._undo_manifest
        if report.already_undone:
            self.dialogs.info(S.UNDO_DONE, report.summary())
            return
        if not self.dialogs.ask(
            S.CONFIRM_UNDO_TITLE, S.CONFIRM_UNDO.format(summary=report.summary())
        ):
            return
        if self.task_thread is not None:
            self.task_thread.wait()
        worker = UndoWorker(manifest)
        worker.finished.connect(self._on_undo_finished)
        worker.failed.connect(self._on_undo_failed)
        self._run(worker)

    def _on_undo_finished(self, report: UndoReport) -> None:
        self.undo_button.setEnabled(False)
        self.result_text.appendPlainText("\n" + S.UNDO_DONE + ":\n" + report.summary())
        self.dialogs.info(S.UNDO_DONE, report.summary())

    # ==================================================================== closing

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 - Qt API
        """Stop background work cleanly before closing."""
        self.cancel_work()
        if self.task_thread is not None:
            self.task_thread.wait()
        self.loader.wait()
        super().closeEvent(event)

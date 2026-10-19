"""Duplicates page: groups on the left (checkable), copies side by side on the right."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon, QImage, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from face_sorter.gui import strings as S
from face_sorter.gui.thumbnails import ThumbnailLoader
from face_sorter.services.dedupe import (
    DedupeResult,
    DupKind,
    DuplicateGroup,
    Photo,
    effective_selection,
    human_size,
)

ROLE = Qt.ItemDataRole.UserRole
PREVIEW_SIZE = 220


class DuplicatesPage(QWidget):
    """Shows a :class:`DedupeResult`; the main window wires the action buttons."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.result: DedupeResult | None = None
        self.loader = ThumbnailLoader(self, size=PREVIEW_SIZE)
        self.loader.ready.connect(self._on_thumbnail)
        self._thumbs: dict[Path, QIcon] = {}
        placeholder = QPixmap(PREVIEW_SIZE, PREVIEW_SIZE)
        placeholder.fill(Qt.GlobalColor.lightGray)
        self._placeholder = QIcon(placeholder)

        layout = QVBoxLayout(self)
        self.title = QLabel()
        layout.addWidget(self.title)
        hint = QLabel(S.DUP_HINT)
        hint.setWordWrap(True)
        layout.addWidget(hint)

        splitter = QSplitter()
        self.group_list = QListWidget()
        self.group_list.currentRowChanged.connect(lambda _row: self.show_group())
        self.group_list.itemChanged.connect(lambda _item: self._update_buttons())
        splitter.addWidget(self.group_list)

        right = QWidget()
        right_lay = QVBoxLayout(right)
        self.photo_list = QListWidget()
        self.photo_list.setViewMode(QListWidget.ViewMode.IconMode)
        self.photo_list.setIconSize(QSize(PREVIEW_SIZE, PREVIEW_SIZE))
        self.photo_list.setGridSize(QSize(PREVIEW_SIZE + 40, PREVIEW_SIZE + 90))
        self.photo_list.setUniformItemSizes(True)
        self.photo_list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.photo_list.setMovement(QListWidget.Movement.Static)
        self.photo_list.setWordWrap(True)
        self.photo_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.photo_list.itemSelectionChanged.connect(self._update_buttons)
        right_lay.addWidget(self.photo_list)
        row = QHBoxLayout()
        self.keep_button = QPushButton(S.DUP_KEEP_THIS)
        self.keep_button.clicked.connect(self.keep_selected)
        row.addWidget(self.keep_button)
        row.addStretch()
        right_lay.addLayout(row)
        splitter.addWidget(right)
        splitter.setSizes([320, 780])
        layout.addWidget(splitter, 1)

        bottom = QHBoxLayout()
        self.back_button = QPushButton(S.BACK)
        self.preview_button = QPushButton(S.PREVIEW)
        self.move_button = QPushButton(S.DUP_MOVE)
        self.trash_button = QPushButton(S.DUP_TRASH)
        bottom.addWidget(self.back_button)
        bottom.addStretch()
        for b in (self.preview_button, self.trash_button, self.move_button):
            bottom.addWidget(b)
        layout.addLayout(bottom)

    # -- data ----------------------------------------------------------------------

    def load(self, result: DedupeResult) -> None:
        """Show ``result``: exact groups checked, near groups unchecked."""
        self.result = result
        self._thumbs.clear()
        self.title.setText(S.DUP_TITLE.format(folder=result.root))
        self.group_list.blockSignals(True)
        self.group_list.clear()
        for g in result.groups:
            text = (
                S.DUP_EXACT_ITEM.format(n=len(g.photos))
                if g.kind is DupKind.EXACT
                else S.DUP_NEAR_ITEM.format(n=len(g.photos), d=g.distance)
            )
            item = QListWidgetItem(f"{text}\n{g.keep.path.name}")
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            checked = g.kind is DupKind.EXACT
            item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
            item.setData(ROLE, g.id)
            self.group_list.addItem(item)
        if not result.groups:
            self.group_list.addItem(QListWidgetItem(S.DUP_NONE))
        self.group_list.blockSignals(False)
        self.group_list.setCurrentRow(0)
        self.show_group()

    def selected_ids(self) -> list[str]:
        """Checked group ids, minus exact groups absorbed by a checked near group."""
        if self.result is None:
            return []
        checked = [
            self.group_list.item(i).data(ROLE)
            for i in range(self.group_list.count())
            if self.group_list.item(i).data(ROLE)
            and self.group_list.item(i).checkState() == Qt.CheckState.Checked
        ]
        return effective_selection(self.result, checked)

    def n_selected_files(self) -> int:
        """How many files the checked groups would remove."""
        assert self.result is not None
        return sum(len(self.result.group(g).duplicates) for g in self.selected_ids())

    def current_group(self) -> DuplicateGroup | None:
        """The group shown on the right."""
        item = self.group_list.currentItem()
        if self.result is None or item is None or not item.data(ROLE):
            return None
        return self.result.group(item.data(ROLE))

    # -- view ----------------------------------------------------------------------

    def show_group(self) -> None:
        """Show the copies of the current group side by side."""
        self.photo_list.clear()
        group = self.current_group()
        if group is not None:
            for photo in group.photos:
                item = QListWidgetItem(self._icon(photo.path), self._label(group, photo))
                item.setToolTip(str(photo.path))
                item.setData(ROLE, photo.path)
                self.photo_list.addItem(item)
        self._update_buttons()

    def _label(self, group: DuplicateGroup, photo: Photo) -> str:
        res = f"{photo.hashes.width}×{photo.hashes.height}" if photo.pixels else "?"
        parts = [res, human_size(photo.size)]
        if photo.hashes.taken_at:
            parts.append(photo.hashes.taken_at[:10])
        head = S.DUP_KEEP_MARK if photo.path == group.keep.path else ""
        root = self.result.root if self.result is not None else photo.path.parent
        rel = photo.path.relative_to(root) if photo.path.is_relative_to(root) else photo.path
        return "\n".join(x for x in (head, str(rel), " · ".join(parts)) if x)

    def keep_selected(self) -> None:
        """Keep the selected copy instead of the automatic choice (RF-18 override)."""
        group, items = self.current_group(), self.photo_list.selectedItems()
        if group is None or not items:
            return
        group.set_keep(items[0].data(ROLE))
        row = self.group_list.currentRow()
        item = self.group_list.item(row)
        item.setText(item.text().split("\n")[0] + "\n" + group.keep.path.name)
        self.show_group()

    def _icon(self, path: Path) -> QIcon:
        if path not in self._thumbs:
            self._thumbs[path] = self._placeholder
            self.loader.request([(path, path, None)])
        return self._thumbs[path]

    def _on_thumbnail(self, key: object, image: QImage) -> None:
        icon = QIcon(QPixmap.fromImage(image))
        if isinstance(key, Path):
            self._thumbs[key] = icon
        for i in range(self.photo_list.count()):
            item = self.photo_list.item(i)
            if item.data(ROLE) == key:
                item.setIcon(icon)

    def _update_buttons(self) -> None:
        has_selection = bool(self.selected_ids())
        self.move_button.setEnabled(has_selection)
        self.trash_button.setEnabled(has_selection)
        self.preview_button.setEnabled(self.result is not None)
        group, items = self.current_group(), self.photo_list.selectedItems()
        self.keep_button.setEnabled(
            group is not None and bool(items) and items[0].data(ROLE) != group.keep.path
        )

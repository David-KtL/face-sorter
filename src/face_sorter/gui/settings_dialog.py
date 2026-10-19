"""Settings dialog (RF-14). Spanish only, by decision (see docs/PROGRESO.md)."""

from __future__ import annotations

from dataclasses import replace

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from face_sorter.config import EDITABLE_SETTINGS, OutputMode, Settings
from face_sorter.gui import strings as S

MODE_LABELS = {
    OutputMode.COPY: S.MODE_COPY,
    OutputMode.HARDLINK: S.MODE_HARDLINK,
    OutputMode.MOVE: S.MODE_MOVE,
}


def _double(key: str, decimals: int, step: float, tip: str) -> QDoubleSpinBox:
    _, low, high = EDITABLE_SETTINGS[key]
    box = QDoubleSpinBox()
    box.setRange(low, high)
    box.setDecimals(decimals)
    box.setSingleStep(step)
    box.setToolTip(tip)
    return box


def _int(key: str, tip: str) -> QSpinBox:
    _, low, high = EDITABLE_SETTINGS[key]
    box = QSpinBox()
    box.setRange(int(low), int(high))
    box.setToolTip(tip)
    return box


class SettingsDialog(QDialog):
    """Edit the user settings. ``delete_data_button`` is wired by the main window."""

    def __init__(self, settings: Settings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(S.SETTINGS_TITLE)
        self.base = settings

        self.threshold = _double("clustering.distance_threshold", 2, 0.01, S.SET_THRESHOLD_TIP)
        self.min_group = _int("clustering.min_cluster_size", S.SET_MIN_GROUP_TIP)
        self.min_face = _int("quality.min_face_size", S.SET_MIN_FACE_TIP)
        self.min_score = _double("quality.min_score", 2, 0.01, S.SET_MIN_SCORE_TIP)
        self.min_sharp = _double("quality.min_sharpness", 1, 5.0, S.SET_MIN_SHARP_TIP)
        self.dup_distance = _int("dedupe.max_distance", S.SET_DUP_DISTANCE_TIP)
        self.mode = QComboBox()
        for mode, label in MODE_LABELS.items():
            self.mode.addItem(label, mode)

        form = QFormLayout()
        form.addRow(S.SET_THRESHOLD, self.threshold)
        form.addRow(S.SET_MIN_GROUP, self.min_group)
        form.addRow(S.SET_MIN_FACE, self.min_face)
        form.addRow(S.SET_MIN_SCORE, self.min_score)
        form.addRow(S.SET_MIN_SHARP, self.min_sharp)
        form.addRow(S.SET_DUP_DISTANCE, self.dup_distance)
        form.addRow(S.SET_MODE, self.mode)

        self.defaults_button = QPushButton(S.SET_DEFAULTS)
        self.defaults_button.clicked.connect(lambda: self.show_settings(Settings()))
        self.delete_data_button = QPushButton(S.SET_DELETE_DATA)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.defaults_button)
        layout.addWidget(self.delete_data_button)
        layout.addWidget(self.buttons)
        self.show_settings(settings)

    def show_settings(self, s: Settings) -> None:
        """Fill the fields from ``s``."""
        self.threshold.setValue(s.clustering.distance_threshold)
        self.min_group.setValue(s.clustering.min_cluster_size)
        self.min_face.setValue(s.quality.min_face_size)
        self.min_score.setValue(s.quality.min_score)
        self.min_sharp.setValue(s.quality.min_sharpness)
        self.dup_distance.setValue(s.dedupe.max_distance)
        self.mode.setCurrentIndex(self.mode.findData(s.output_mode))

    def settings(self) -> Settings:
        """The edited settings (paths and non-editable values kept from the original)."""
        b = self.base
        return replace(
            b,
            output_mode=OutputMode(self.mode.currentData()),
            clustering=replace(
                b.clustering,
                distance_threshold=round(self.threshold.value(), 2),
                min_cluster_size=self.min_group.value(),
            ),
            quality=replace(
                b.quality,
                min_face_size=self.min_face.value(),
                min_score=round(self.min_score.value(), 2),
                min_sharpness=round(self.min_sharp.value(), 1),
            ),
            dedupe=replace(b.dedupe, max_distance=self.dup_distance.value()),
        )

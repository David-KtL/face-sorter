"""GUI tests (pytest-qt, offscreen). Use model-free fakes, so they run without models."""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from pytestqt.qtbot import QtBot

from face_sorter.config import OutputMode, Settings
from face_sorter.core.detector import DetectedFace
from face_sorter.core.image_io import BGRImage, sha256_file
from face_sorter.gui.main_window import ROLE, VIEW_EXCLUDED, VIEW_UNCLASSIFIED, MainWindow
from face_sorter.gui.thumbnails import crop_face, to_qimage
from face_sorter.services.pipeline import Pipeline
from tests.fakes import FakeDetector, FakeEmbedder, write_face_image


class FakeDialogs:
    """Scripted answers instead of modal dialogs."""

    def __init__(self) -> None:
        self.answers: dict[str, Any] = {"ask": True, "text": None, "choose": None}
        self.errors: list[str] = []
        self.infos: list[str] = []
        self.shown: list[str] = []
        self.asked: list[str] = []

    def ask(self, title: str, text: str) -> bool:
        self.asked.append(text)
        return bool(self.answers["ask"])

    def info(self, title: str, text: str) -> None:
        self.infos.append(text)

    def error(self, title: str, text: str) -> None:
        self.errors.append(text)

    def text(self, title: str, label: str, default: str) -> str | None:
        value = self.answers["text"]
        return value if value is None else str(value)

    def choose(self, title: str, label: str, items: list[str]) -> str | None:
        value = self.answers["choose"]
        return value if value is None else str(value)

    def folder(self, title: str, start: str) -> str | None:
        return self.answers.get("folder")

    def open_file(self, title: str, start: str, filters: str) -> str | None:
        return self.answers.get("file")

    def show_text(self, title: str, text: str) -> None:
        self.shown.append(text)


class SlowDetector(FakeDetector):
    def detect(self, image: BGRImage) -> list[DetectedFace]:
        time.sleep(0.2)
        return super().detect(image)


@pytest.fixture
def photos(tmp_path: Path) -> Path:
    root = tmp_path / "photos"
    for i in range(3):
        write_face_image(root / f"ana_{i}.png", 50)
        write_face_image(root / f"luis_{i}.png", 150)
    write_face_image(root / "stranger.png", 220)
    write_face_image(root / "landscape.png", 0)
    return root


def make_window(qtbot: QtBot, tmp_path: Path, detector: FakeDetector | None = None) -> MainWindow:
    settings = Settings(cache_path=tmp_path / "cache.sqlite")

    def factory(s: Settings) -> Pipeline:
        return Pipeline(s, detector=detector or FakeDetector(), embedder=FakeEmbedder())

    window = MainWindow(settings, pipeline_factory=factory)
    window.dialogs = FakeDialogs()  # type: ignore[assignment]
    qtbot.addWidget(window)
    return window


@pytest.fixture
def window(qtbot: QtBot, tmp_path: Path) -> Iterator[MainWindow]:
    w = make_window(qtbot, tmp_path)
    yield w
    w.close()


def dialogs(w: MainWindow) -> FakeDialogs:
    assert isinstance(w.dialogs, FakeDialogs)
    return w.dialogs


def scan(qtbot: QtBot, w: MainWindow, photos: Path, out: Path) -> None:
    w.source_edit.setText(str(photos))
    w.output_edit.setText(str(out))
    w.scan_button.click()
    qtbot.waitUntil(lambda: w.pages.currentWidget() is w.review_page, timeout=20_000)


def group_texts(w: MainWindow) -> list[str]:
    return [w.group_list.item(i).text() for i in range(w.group_list.count())]


def select_view(w: MainWindow, view: tuple[str, Any]) -> None:
    for i in range(w.group_list.count()):
        if w.group_list.item(i).data(ROLE) == view:
            w.group_list.setCurrentRow(i)
            return
    raise AssertionError(f"view not found: {view}")


def select_all_faces(w: MainWindow) -> None:
    w.face_list.selectAll()


# -- thumbnails ---------------------------------------------------------------------------


def test_crop_face_and_qimage() -> None:
    img = np.zeros((200, 300, 3), np.uint8)
    img[50:150, 100:200] = (0, 0, 255)  # red square (BGR)
    face = crop_face(img, (100, 50, 100, 100), size=64)
    assert face.shape == (64, 64, 3)
    assert tuple(face[32, 32]) == (0, 0, 255)
    whole = crop_face(img, None, size=64)
    assert whole.shape == (64, 64, 3)
    q = to_qimage(face)
    assert (q.width(), q.height()) == (64, 64)
    assert q.pixelColor(32, 32).red() == 255


# -- scan ---------------------------------------------------------------------------------


def test_scan_runs_in_background_and_shows_groups(
    qtbot: QtBot, window: MainWindow, photos: Path, tmp_path: Path
) -> None:
    scan(qtbot, window, photos, tmp_path / "out")
    assert window.worker is not None
    assert window.worker.thread_id not in (None, threading.get_ident())  # off the GUI thread
    texts = group_texts(window)
    assert texts[:2] == [
        "Persona_001  (3 rostros · 3 fotos)",
        "Persona_002  (3 rostros · 3 fotos)",
    ]
    assert "Sin clasificar (1)" in texts and "Sin rostro (1 fotos)" in texts
    assert window.face_list.count() == 3
    window.loader.wait()
    placeholder = window._placeholder().cacheKey()
    qtbot.waitUntil(lambda: window.face_list.item(0).icon().cacheKey() != placeholder)


def test_scan_validation(qtbot: QtBot, window: MainWindow, photos: Path) -> None:
    window.scan_button.click()
    window.source_edit.setText(str(photos / "missing"))
    window.output_edit.setText(str(photos))
    window.scan_button.click()
    window.source_edit.setText(str(photos))
    window.scan_button.click()
    assert len(dialogs(window).errors) == 3
    assert window.pages.currentWidget() is window.setup_page


def test_scan_can_be_cancelled(qtbot: QtBot, tmp_path: Path, photos: Path) -> None:
    w = make_window(qtbot, tmp_path, SlowDetector())
    w.source_edit.setText(str(photos))
    w.output_edit.setText(str(tmp_path / "out"))
    w.scan_button.click()
    assert w.cancel_button.isEnabled()
    qtbot.waitUntil(lambda: w.progress.value() >= 1, timeout=10_000)
    w.cancel_button.click()
    qtbot.waitUntil(lambda: w.scan_button.isEnabled(), timeout=10_000)
    assert "cancelado" in w.status.text()
    assert w.pages.currentWidget() is w.setup_page
    w.close()


def test_close_during_scan_stops_cleanly(qtbot: QtBot, tmp_path: Path, photos: Path) -> None:
    w = make_window(qtbot, tmp_path, SlowDetector())
    w.source_edit.setText(str(photos))
    w.output_edit.setText(str(tmp_path / "out"))
    w.scan_button.click()
    w.close()
    assert not w.busy


def test_browse_fills_the_field(window: MainWindow, tmp_path: Path) -> None:
    dialogs(window).answers["folder"] = str(tmp_path)
    window._browse(window.source_edit, "x")
    assert window.source_edit.text() == str(tmp_path)


# -- review -------------------------------------------------------------------------------


def test_rename_and_invalid_names(
    qtbot: QtBot, window: MainWindow, photos: Path, tmp_path: Path
) -> None:
    scan(qtbot, window, photos, tmp_path / "out")
    d = dialogs(window)
    d.answers["text"] = "Ana"
    window.rename_button.click()
    assert group_texts(window)[0].startswith("Ana  ")

    window.group_list.setCurrentRow(1)
    d.answers["text"] = "ana"  # duplicate (case-insensitive)
    window.rename_button.click()
    assert d.errors and "Ya existe" in d.errors[-1]

    d.answers["text"] = "Luis?"
    window.rename_button.click()
    assert "Luis_" in d.infos[-1]
    assert any(t.startswith("Luis_  ") for t in group_texts(window))


def test_merge_split_move_exclude_restore(
    qtbot: QtBot, window: MainWindow, photos: Path, tmp_path: Path
) -> None:
    scan(qtbot, window, photos, tmp_path / "out")
    s = window.session
    assert s is not None

    window.group_list.item(0).setSelected(True)
    window.group_list.item(1).setSelected(True)
    assert window.merge_button.isEnabled()
    window.merge_button.click()
    assert [len(g.faces) for g in s.groups()] == [6]

    window.face_list.item(0).setSelected(True)
    window.split_button.click()
    assert sorted(len(g.faces) for g in s.groups()) == [1, 5]

    select_view(window, (VIEW_UNCLASSIFIED, None))
    select_all_faces(window)
    dialogs(window).answers["choose"] = s.groups()[0].name
    window.move_button.click()
    assert s.unclassified_faces() == []

    window.group_list.setCurrentRow(0)
    window.face_list.item(0).setSelected(True)
    window.exclude_face_button.click()
    assert len(s.excluded_face_list()) == 1

    select_view(window, (VIEW_EXCLUDED, None))
    select_all_faces(window)
    assert window.restore_button.isEnabled()
    window.restore_button.click()
    assert s.excluded_face_list() == []

    window.group_list.setCurrentRow(0)
    window.face_list.item(0).setSelected(True)
    window.exclude_photo_button.click()
    assert len(s.excluded_images) == 1

    window.preview_button.click()
    assert "excluded: 1" in dialogs(window).shown[-1]


def test_merge_needs_two_groups(
    qtbot: QtBot, window: MainWindow, photos: Path, tmp_path: Path
) -> None:
    scan(qtbot, window, photos, tmp_path / "out")
    window.merge_groups()
    assert "dos grupos" in dialogs(window).errors[-1]


# -- apply / undo ---------------------------------------------------------------------------


def test_apply_copy_then_undo(
    qtbot: QtBot, window: MainWindow, photos: Path, tmp_path: Path
) -> None:
    before = {p.name: sha256_file(p) for p in photos.iterdir()}
    out = tmp_path / "out"
    scan(qtbot, window, photos, out)
    dialogs(window).answers["text"] = "Ana"
    window.rename_button.click()

    window.apply_button.click()
    qtbot.waitUntil(lambda: window.pages.currentWidget() is window.result_page, timeout=20_000)
    assert window.worker is not None and window.worker.thread_id != threading.get_ident()
    assert sorted(p.name for p in (out / "Ana").iterdir()) == [
        "ana_0.png",
        "ana_1.png",
        "ana_2.png",
    ]
    assert "Created: 8" in window.result_text.toPlainText()
    assert before == {p.name: sha256_file(p) for p in photos.iterdir()}  # originals intact

    window.undo_button.click()
    qtbot.waitUntil(lambda: not window.undo_button.isEnabled(), timeout=20_000)
    assert "delete 8" in dialogs(window).asked[-1]  # preview shown before undoing
    assert list(out.rglob("*.png")) == []


def test_move_asks_and_respects_no(
    qtbot: QtBot, window: MainWindow, photos: Path, tmp_path: Path
) -> None:
    out = tmp_path / "out"
    scan(qtbot, window, photos, out)
    window.mode_combo.setCurrentIndex(window.mode_combo.findData(OutputMode.MOVE))
    dialogs(window).answers["ask"] = False
    window.apply_button.click()
    assert "8 fotos" in dialogs(window).asked[-1]
    assert window.pages.currentWidget() is window.review_page
    assert not out.exists()

    dialogs(window).answers["ask"] = True
    window.apply_button.click()
    qtbot.waitUntil(lambda: window.pages.currentWidget() is window.result_page, timeout=20_000)
    assert sorted(p.name for p in photos.iterdir()) == []
    window.undo_button.click()
    qtbot.waitUntil(lambda: not window.undo_button.isEnabled(), timeout=20_000)
    assert len(list(photos.iterdir())) == 8


def test_undo_from_manifest_file(
    qtbot: QtBot, window: MainWindow, photos: Path, tmp_path: Path
) -> None:
    out = tmp_path / "out"
    scan(qtbot, window, photos, out)
    window.apply_button.click()
    qtbot.waitUntil(lambda: window.pages.currentWidget() is window.result_page, timeout=20_000)
    manifest = next(out.glob("manifest_*.json"))
    dialogs(window).answers["file"] = str(manifest)
    window.undo_from_file()
    qtbot.waitUntil(lambda: bool(dialogs(window).infos), timeout=20_000)
    assert list(out.rglob("*.png")) == []

    window.undo_from_file()  # second time: already undone
    qtbot.waitUntil(lambda: len(dialogs(window).infos) == 2, timeout=20_000)
    assert "already undone" in dialogs(window).infos[-1]

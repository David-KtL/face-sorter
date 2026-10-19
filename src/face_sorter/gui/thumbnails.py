"""Face and photo thumbnails, decoded in a thread pool (never in the GUI thread)."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from pathlib import Path

import cv2
import numpy as np
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal
from PySide6.QtGui import QImage

from face_sorter.core.image_io import BGRImage, ImageLoadError, load_image

log = logging.getLogger(__name__)

THUMB_SIZE = 112
FACE_MARGIN = 0.3  # extra context around the face box, as a fraction of its size

Box = tuple[float, float, float, float]


def crop_face(image: BGRImage, bbox: Box | None, size: int = THUMB_SIZE) -> BGRImage:
    """Square crop around ``bbox`` (with margin), resized to ``size``; whole photo if None."""
    h, w = image.shape[:2]
    if bbox is None:
        side = max(h, w)
        canvas = np.zeros((side, side, 3), np.uint8)
        y0, x0 = (side - h) // 2, (side - w) // 2
        canvas[y0 : y0 + h, x0 : x0 + w] = image
        crop = canvas
    else:
        x, y, bw, bh = bbox
        side = max(bw, bh) * (1 + 2 * FACE_MARGIN)
        cx, cy = x + bw / 2, y + bh / 2
        x0, y0 = int(max(0, cx - side / 2)), int(max(0, cy - side / 2))
        x1, y1 = int(min(w, cx + side / 2)), int(min(h, cy + side / 2))
        crop = image[y0:y1, x0:x1] if x1 > x0 and y1 > y0 else image
    return np.asarray(cv2.resize(crop, (size, size), interpolation=cv2.INTER_AREA), np.uint8)


def to_qimage(bgr: BGRImage) -> QImage:
    """Convert a BGR array to a standalone QImage (safe to create in any thread)."""
    rgb = np.ascontiguousarray(bgr[:, :, ::-1])
    h, w = rgb.shape[:2]
    return QImage(rgb.data, w, h, 3 * w, QImage.Format.Format_RGB888).copy()


class _Job(QRunnable):
    def __init__(
        self, loader: ThumbnailLoader, path: Path, requests: Sequence[tuple[object, Box | None]]
    ):
        super().__init__()
        self.loader, self.path, self.requests = loader, path, requests

    def run(self) -> None:
        try:
            image = load_image(self.path)
        except ImageLoadError as exc:
            log.warning("Thumbnail unavailable for %s: %s", self.path, exc)
            return
        for key, bbox in self.requests:
            self.loader.ready.emit(key, to_qimage(crop_face(image, bbox, self.loader.size)))


class ThumbnailLoader(QObject):
    """Loads thumbnails asynchronously; emits ``ready(key, QImage)`` for each one."""

    ready = Signal(object, QImage)

    def __init__(self, parent: QObject | None = None, size: int = THUMB_SIZE) -> None:
        super().__init__(parent)
        self.size = size
        self.pool = QThreadPool(self)

    def request(self, items: Sequence[tuple[object, Path, Box | None]]) -> None:
        """Queue ``(key, image path, face box or None)`` items; each photo is decoded once."""
        by_path: dict[Path, list[tuple[object, Box | None]]] = {}
        for key, path, bbox in items:
            by_path.setdefault(path, []).append((key, bbox))
        for path, requests in by_path.items():
            self.pool.start(_Job(self, path, requests))

    def wait(self, msecs: int = 30_000) -> bool:
        """Block until queued jobs finish (for tests and shutdown)."""
        return self.pool.waitForDone(msecs)

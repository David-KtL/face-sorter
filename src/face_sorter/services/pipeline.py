"""Processing pipeline: scan -> cache -> detect -> embed -> quality -> cluster.

Read-only on the source photos. Results are cached per image as they are computed,
so a cancelled or interrupted scan resumes where it stopped (RNF-04). A broken image
is logged and skipped, never stopping the scan (RNF-07).
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
from pathlib import Path
from types import TracebackType

import numpy as np

from face_sorter.config import Settings
from face_sorter.core.cache import FaceCache, FaceRecord, ImageStatus
from face_sorter.core.clustering import UNCLASSIFIED, cluster_embeddings
from face_sorter.core.detector import DetectedFace, FaceDetector
from face_sorter.core.embedder import Embedder, Embedding, SFaceEmbedder
from face_sorter.core.hashing import compute_hashes
from face_sorter.core.image_io import ImageLoadError, decode_image, read_bytes, sha256_bytes
from face_sorter.core.quality import FaceMetrics, QualityReport, assess, sharpness
from face_sorter.core.scanner import scan

log = logging.getLogger(__name__)


class ScanCancelled(Exception):
    """The scan was cancelled. Already processed images remain cached."""


@dataclass(frozen=True)
class FaceInfo:
    """One face of one image, with its quality verdict and cluster label."""

    image: Path
    index: int
    face: DetectedFace
    sharpness: float
    embedding: Embedding
    quality: QualityReport
    label: int = UNCLASSIFIED

    @property
    def usable(self) -> bool:
        """True if the face passed the quality filter (and so was clustered)."""
        return self.quality.ok


@dataclass(frozen=True)
class ImageInfo:
    """Processing result of one image."""

    path: Path
    status: ImageStatus
    faces: tuple[FaceInfo, ...] = ()
    error: str | None = None
    from_cache: bool = False


@dataclass(frozen=True)
class Progress:
    """Progress event, emitted after each image."""

    done: int
    total: int
    path: Path
    from_cache: bool


@dataclass(frozen=True)
class ScanResult:
    """Every processed image, with cluster labels assigned to usable faces."""

    root: Path
    images: tuple[ImageInfo, ...]
    n_clusters: int

    @property
    def faces(self) -> list[FaceInfo]:
        """All faces of all images, in scan order."""
        return [f for img in self.images for f in img.faces]


def cache_fingerprint(settings: Settings, embedder_name: str = SFaceEmbedder.name) -> str:
    """Fingerprint of the face models; opening the cache with another one empties its faces."""
    return f"{embedder_name}|{settings.detector.fingerprint()}"


ProgressCallback = Callable[[Progress], None]
CancelCheck = Callable[[], bool]


class Pipeline:
    """Runs the full analysis. Use as a context manager so the cache gets closed.

    Models are loaded lazily, only when an image is not in the cache.
    """

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        detector: FaceDetector | None = None,
        embedder: Embedder | None = None,
        cache: FaceCache | None = None,
    ) -> None:
        self.settings = settings or Settings()
        self._detector = detector
        self._embedder = embedder
        embedder_name = embedder.name if embedder else SFaceEmbedder.name
        self.fingerprint = cache_fingerprint(self.settings, embedder_name)
        self._owns_cache = cache is None
        self.cache = cache or FaceCache(self.settings.cache_path, self.fingerprint)

    # -- lifecycle -------------------------------------------------------------------

    def close(self) -> None:
        """Close the cache if this pipeline opened it."""
        if self._owns_cache:
            self.cache.close()

    def __enter__(self) -> Pipeline:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    @property
    def detector(self) -> FaceDetector:
        """The face detector (loaded on first use)."""
        if self._detector is None:
            self._detector = FaceDetector(self.settings.detector_model_path, self.settings.detector)
        return self._detector

    @property
    def embedder(self) -> Embedder:
        """The embedder (loaded on first use)."""
        if self._embedder is None:
            self._embedder = SFaceEmbedder(self.settings.recognizer_model_path)
        return self._embedder

    # -- processing ------------------------------------------------------------------

    def process_image(self, path: Path) -> ImageInfo:
        """Analyse one image, using the cache when the file did not change."""
        entry = self.cache.lookup(path)
        if entry is not None:
            if entry.status is ImageStatus.ERROR:
                return ImageInfo(path, ImageStatus.ERROR, error=entry.error, from_cache=True)
            faces = tuple(
                self._face_info(path, i, c.face, c.sharpness, c.embedding)
                for i, c in enumerate(self.cache.faces(entry.id))
            )
            return ImageInfo(path, ImageStatus.OK, faces, from_cache=True)

        sha: str | None = None
        try:
            data = read_bytes(path)
            sha = sha256_bytes(data)
            image = decode_image(data)
        except ImageLoadError as exc:
            log.warning("Cannot read %s: %s", path, exc)
            self.cache.store_error(path, str(exc), sha)
            return ImageInfo(path, ImageStatus.ERROR, error=str(exc))

        # Free by-product for duplicate detection (phase 5): the image is already decoded.
        if self.cache.lookup_hashes(path) is None:
            self.cache.store_hashes(path, compute_hashes(data, image))

        try:
            records = []
            for face in self.detector.detect(image):
                crop = self.embedder.align(image, face)
                records.append(FaceRecord(face, sharpness(crop), self.embedder.embed_aligned(crop)))
        except (FileNotFoundError, MemoryError):
            raise  # Missing models or out of memory: not a per-image problem.
        except Exception as exc:  # noqa: BLE001 - RNF-07: one bad image must not stop the scan.
            log.exception("Failed to analyse %s", path)
            return ImageInfo(path, ImageStatus.ERROR, error=f"{type(exc).__name__}: {exc}")

        self.cache.store_faces(path, sha, records)
        faces = tuple(
            self._face_info(path, i, r.face, r.sharpness, r.embedding)
            for i, r in enumerate(records)
        )
        return ImageInfo(path, ImageStatus.OK, faces)

    def _face_info(
        self, path: Path, index: int, face: DetectedFace, sharp: float, emb: Embedding
    ) -> FaceInfo:
        report = assess(FaceMetrics(face.min_side, face.score, sharp), self.settings.quality)
        return FaceInfo(path, index, face, sharp, emb, report)

    def run(
        self,
        root: Path,
        *,
        exclude: Iterable[Path] = (),
        progress: ProgressCallback | None = None,
        cancel: CancelCheck | None = None,
    ) -> ScanResult:
        """Analyse every image under ``root`` and cluster the usable faces.

        Raises:
            ScanCancelled: if ``cancel()`` returns True (checked before each image).
            NotADirectoryError: if ``root`` is not a folder.
        """
        root = Path(root)
        paths = list(scan(root, exclude=exclude))
        images: list[ImageInfo] = []
        for done, path in enumerate(paths, start=1):
            if cancel is not None and cancel():
                raise ScanCancelled(f"Cancelled after {done - 1} of {len(paths)} images")
            info = self.process_image(path)
            images.append(info)
            if progress is not None:
                progress(Progress(done, len(paths), path, info.from_cache))
        return self.cluster(root, images)

    def cluster(self, root: Path, images: list[ImageInfo]) -> ScanResult:
        """Assign cluster labels to the usable faces of ``images``."""
        usable = [
            (i, j) for i, img in enumerate(images) for j, f in enumerate(img.faces) if f.usable
        ]
        if not usable:
            return ScanResult(root, tuple(images), 0)
        matrix = np.stack([images[i].faces[j].embedding for i, j in usable])
        labels = cluster_embeddings(matrix, self.settings.clustering)

        new_faces = [list(img.faces) for img in images]
        for (i, j), label in zip(usable, labels.tolist(), strict=True):
            new_faces[i][j] = replace(new_faces[i][j], label=label)
        result = tuple(
            replace(img, faces=tuple(faces)) for img, faces in zip(images, new_faces, strict=True)
        )
        n_clusters = max(labels.tolist()) + 1  # labels are 0..k-1, or -1 if none
        return ScanResult(root, result, n_clusters)

"""SQLite cache of detections and embeddings per image (RF-05, RNF-04).

An image is re-processed only if it changed: same size and mtime is a hit; if the
mtime changed but the content hash is the same, it is still a hit. Cached data is
tied to a *fingerprint* of the detector and embedder: if either changes, the cache
is emptied automatically.
"""

from __future__ import annotations

import json
import os
import sqlite3
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from types import TracebackType

import numpy as np

from face_sorter.core.detector import DetectedFace
from face_sorter.core.embedder import Embedding
from face_sorter.core.hashing import ImageHashes
from face_sorter.core.image_io import sha256_file
from face_sorter.core.quality import FaceMetrics

SCHEMA_VERSION = "2"
# Versions that can be upgraded in place (new tables only, no data loss).
_UPGRADABLE = {"1"}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS images (
    id         INTEGER PRIMARY KEY,
    path       TEXT NOT NULL,
    path_key   TEXT NOT NULL UNIQUE,
    size       INTEGER NOT NULL,
    mtime_ns   INTEGER NOT NULL,
    hash       TEXT,
    status     TEXT NOT NULL CHECK (status IN ('ok', 'error')),
    error      TEXT,
    scanned_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS faces (
    id         INTEGER PRIMARY KEY,
    image_id   INTEGER NOT NULL REFERENCES images(id) ON DELETE CASCADE,
    face_index INTEGER NOT NULL,
    bbox       TEXT NOT NULL,
    landmarks  TEXT NOT NULL,
    score      REAL NOT NULL,
    sharpness  REAL NOT NULL,
    embedding  BLOB NOT NULL,
    UNIQUE (image_id, face_index)
);
CREATE INDEX IF NOT EXISTS idx_faces_image ON faces(image_id);
-- v2: hashes for duplicate detection. Independent of the face models' fingerprint.
CREATE TABLE IF NOT EXISTS image_hashes (
    path_key TEXT PRIMARY KEY,
    path     TEXT NOT NULL,
    size     INTEGER NOT NULL,
    mtime_ns INTEGER NOT NULL,
    sha256   TEXT NOT NULL,
    phash    INTEGER,
    width    INTEGER,
    height   INTEGER,
    taken_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_hashes_sha ON image_hashes(sha256);
"""

_EMBEDDING_DTYPE = np.dtype("<f4")


class ImageStatus(StrEnum):
    """Processing result of an image."""

    OK = "ok"
    ERROR = "error"


@dataclass(frozen=True)
class FaceRecord:
    """A processed face, ready to be stored."""

    face: DetectedFace
    sharpness: float
    embedding: Embedding


@dataclass(frozen=True)
class ImageEntry:
    """A cached image row."""

    id: int
    path: str
    size: int
    mtime_ns: int
    sha256: str | None
    status: ImageStatus
    error: str | None


@dataclass(frozen=True)
class CachedFace:
    """A face loaded from the cache."""

    id: int
    image_id: int
    face: DetectedFace
    sharpness: float
    embedding: Embedding

    @property
    def metrics(self) -> FaceMetrics:
        """Quality metrics, to be checked with :func:`face_sorter.core.quality.assess`."""
        return FaceMetrics(self.face.min_side, self.face.score, self.sharpness)


def path_key(path: Path) -> str:
    """Normalized absolute path used as the cache key (case-insensitive on Windows)."""
    return os.path.normcase(str(Path(path).resolve()))


class FaceCache:
    """SQLite-backed cache. Not thread-safe: use one instance per thread."""

    def __init__(self, db_path: Path, fingerprint: str) -> None:
        """Open (or create) the cache at ``db_path``.

        If ``fingerprint`` differs from the stored one, all cached data is discarded.
        """
        self.db_path = Path(db_path)
        self.fingerprint = fingerprint
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.executescript(_SCHEMA)
        self._check_fingerprint()

    # -- lifecycle -------------------------------------------------------------------

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()

    def __enter__(self) -> FaceCache:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def _meta(self, key: str) -> str | None:
        row = self._conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return None if row is None else str(row["value"])

    def _check_fingerprint(self) -> None:
        version = self._meta("schema_version")
        if version in _UPGRADABLE and self._meta("fingerprint") == self.fingerprint:
            with self._conn:  # tables were added by _SCHEMA; just record the upgrade
                self._conn.execute(
                    "UPDATE meta SET value = ? WHERE key = 'schema_version'", (SCHEMA_VERSION,)
                )
            return
        if version == SCHEMA_VERSION and self._meta("fingerprint") == self.fingerprint:
            return
        with self._conn:
            self._conn.execute("DELETE FROM faces")
            self._conn.execute("DELETE FROM images")
            self._conn.executemany(
                "INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)",
                [("schema_version", SCHEMA_VERSION), ("fingerprint", self.fingerprint)],
            )

    # -- queries ---------------------------------------------------------------------

    def lookup(self, path: Path) -> ImageEntry | None:
        """Return the cached entry for ``path`` if the file did not change, else None.

        A file whose mtime changed but whose content hash is identical is a hit; its
        stored mtime is refreshed.
        """
        try:
            st = Path(path).stat()
        except OSError:
            return None
        row = self._conn.execute(
            "SELECT * FROM images WHERE path_key = ?", (path_key(path),)
        ).fetchone()
        if row is None or row["size"] != st.st_size:
            return None
        if row["mtime_ns"] == st.st_mtime_ns:
            return _to_entry(row)
        if row["hash"] and sha256_file(Path(path)) == row["hash"]:
            with self._conn:
                self._conn.execute(
                    "UPDATE images SET mtime_ns = ? WHERE id = ?", (st.st_mtime_ns, row["id"])
                )
            return self.get(row["id"])
        return None

    def get(self, image_id: int) -> ImageEntry | None:
        """Return the image with ``image_id``, or None."""
        row = self._conn.execute("SELECT * FROM images WHERE id = ?", (image_id,)).fetchone()
        return None if row is None else _to_entry(row)

    def faces(self, image_id: int) -> list[CachedFace]:
        """Faces of one image, in detection order."""
        rows = self._conn.execute(
            "SELECT * FROM faces WHERE image_id = ? ORDER BY face_index", (image_id,)
        )
        return [_to_face(r) for r in rows]

    def iter_faces(self) -> Iterator[CachedFace]:
        """Every cached face (for clustering)."""
        for row in self._conn.execute("SELECT * FROM faces ORDER BY image_id, face_index"):
            yield _to_face(row)

    def count_images(self) -> int:
        """Number of cached images."""
        return int(self._conn.execute("SELECT COUNT(*) FROM images").fetchone()[0])

    # -- writes ----------------------------------------------------------------------

    def store_faces(
        self, path: Path, sha256: str | None, faces: Sequence[FaceRecord]
    ) -> ImageEntry:
        """Store a successfully processed image (possibly with zero faces)."""
        with self._conn:
            image_id = self._upsert_image(path, sha256, ImageStatus.OK, None)
            self._conn.execute("DELETE FROM faces WHERE image_id = ?", (image_id,))
            self._conn.executemany(
                "INSERT INTO faces(image_id, face_index, bbox, landmarks, score, sharpness,"
                " embedding) VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        image_id,
                        i,
                        json.dumps(rec.face.bbox),
                        json.dumps(rec.face.landmarks),
                        rec.face.score,
                        float(rec.sharpness),
                        np.asarray(rec.embedding, dtype=_EMBEDDING_DTYPE).tobytes(),
                    )
                    for i, rec in enumerate(faces)
                ],
            )
        entry = self.get(image_id)
        assert entry is not None
        return entry

    def store_error(self, path: Path, message: str, sha256: str | None = None) -> ImageEntry:
        """Record that ``path`` could not be processed (it will be retried if it changes)."""
        with self._conn:
            image_id = self._upsert_image(path, sha256, ImageStatus.ERROR, message)
            self._conn.execute("DELETE FROM faces WHERE image_id = ?", (image_id,))
        entry = self.get(image_id)
        assert entry is not None
        return entry

    def clear(self) -> None:
        """Delete every cached image, face and hash (privacy: 'delete local data')."""
        with self._conn:
            self._conn.execute("DELETE FROM faces")
            self._conn.execute("DELETE FROM images")
            self._conn.execute("DELETE FROM image_hashes")

    # -- duplicate hashes ------------------------------------------------------------

    def lookup_hashes(self, path: Path) -> ImageHashes | None:
        """Cached hashes of ``path`` if its size and mtime did not change, else None."""
        try:
            st = Path(path).stat()
        except OSError:
            return None
        row = self._conn.execute(
            "SELECT * FROM image_hashes WHERE path_key = ?", (path_key(path),)
        ).fetchone()
        if row is None or row["size"] != st.st_size or row["mtime_ns"] != st.st_mtime_ns:
            return None
        phash = None if row["phash"] is None else _to_unsigned(row["phash"])
        return ImageHashes(row["sha256"], phash, row["width"], row["height"], row["taken_at"])

    def store_hashes(self, path: Path, hashes: ImageHashes) -> None:
        """Store (or replace) the hashes of ``path``."""
        st = Path(path).stat()
        phash = None if hashes.phash is None else _to_signed(hashes.phash)
        with self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO image_hashes(path_key, path, size, mtime_ns, sha256,"
                " phash, width, height, taken_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    path_key(path),
                    str(Path(path).resolve()),
                    st.st_size,
                    st.st_mtime_ns,
                    hashes.sha256,
                    phash,
                    hashes.width,
                    hashes.height,
                    hashes.taken_at,
                ),
            )

    def _upsert_image(
        self, path: Path, sha256: str | None, status: ImageStatus, error: str | None
    ) -> int:
        st = Path(path).stat()
        now = datetime.now(UTC).isoformat(timespec="seconds")
        row = self._conn.execute(
            "INSERT INTO images(path, path_key, size, mtime_ns, hash, status, error,"
            " scanned_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
            " ON CONFLICT(path_key) DO UPDATE SET path = excluded.path, size = excluded.size,"
            " mtime_ns = excluded.mtime_ns, hash = excluded.hash, status = excluded.status,"
            " error = excluded.error, scanned_at = excluded.scanned_at"
            " RETURNING id",
            (
                str(Path(path).resolve()),
                path_key(path),
                st.st_size,
                st.st_mtime_ns,
                sha256,
                status.value,
                error,
                now,
            ),
        ).fetchone()
        return int(row[0])


def _to_signed(value: int) -> int:
    """SQLite INTEGER is signed 64-bit: store an unsigned 64-bit hash in two's complement."""
    return value - (1 << 64) if value >= 1 << 63 else value


def _to_unsigned(value: int) -> int:
    return value + (1 << 64) if value < 0 else value


def _to_entry(row: sqlite3.Row) -> ImageEntry:
    return ImageEntry(
        id=row["id"],
        path=row["path"],
        size=row["size"],
        mtime_ns=row["mtime_ns"],
        sha256=row["hash"],
        status=ImageStatus(row["status"]),
        error=row["error"],
    )


def _to_face(row: sqlite3.Row) -> CachedFace:
    bbox = tuple(json.loads(row["bbox"]))
    landmarks = tuple(tuple(p) for p in json.loads(row["landmarks"]))
    face = DetectedFace.from_values(bbox, landmarks, row["score"])  # type: ignore[arg-type]
    embedding = np.frombuffer(row["embedding"], dtype=_EMBEDDING_DTYPE).astype(np.float32)
    return CachedFace(row["id"], row["image_id"], face, row["sharpness"], embedding)

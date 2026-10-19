"""Descarga el dataset público LFW (Labeled Faces in the Wild) a ./data/lfw para los tests.

Usa el mismo espejo y SHA-256 que scikit-learn. `data/` está ignorado en git: nunca se
commitean estas fotos.
"""

from __future__ import annotations

import hashlib
import sys
import tarfile
import urllib.request
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
ARCHIVE_URL = "https://ndownloader.figshare.com/files/5976018"
ARCHIVE_SHA256 = "055f7d9c632d7370e6fb4afc7468d40f970c34a80d4c6f50ffec63f5a8d536c0"
ARCHIVE_NAME = "lfw.tgz"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    target = DATA_DIR / "lfw"
    if target.is_dir() and any(target.iterdir()):
        print(f"[ok] LFW ya existe en {target}")
        return 0

    archive = DATA_DIR / ARCHIVE_NAME
    if not (archive.exists() and sha256(archive) == ARCHIVE_SHA256):
        print("[..] Descargando LFW (~180 MB)")
        tmp = archive.with_suffix(".part")
        try:
            urllib.request.urlretrieve(ARCHIVE_URL, tmp)  # noqa: S310
        except Exception as exc:  # noqa: BLE001
            print(f"[error] descarga: {exc}", file=sys.stderr)
            tmp.unlink(missing_ok=True)
            return 1
        digest = sha256(tmp)
        if digest != ARCHIVE_SHA256:
            print(f"[error] sha256 inesperado {digest}", file=sys.stderr)
            tmp.unlink(missing_ok=True)
            return 1
        tmp.replace(archive)

    print("[..] Extrayendo")
    with tarfile.open(archive, "r:gz") as tar:
        tar.extractall(DATA_DIR, filter="data")  # el filtro bloquea rutas fuera de DATA_DIR
    archive.unlink()
    n = sum(1 for _ in target.rglob("*.jpg"))
    print(f"[ok] LFW extraído en {target} ({n} imágenes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

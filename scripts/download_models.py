"""Descarga los modelos ONNX (YuNet y SFace) desde OpenCV Zoo a ./models."""

from __future__ import annotations

import hashlib
import sys
import urllib.request
from pathlib import Path

MODELS_DIR = Path(__file__).resolve().parent.parent / "models"

BASE = "https://github.com/opencv/opencv_zoo/raw/main/models"
MODELS = {
    "face_detection_yunet_2023mar.onnx": f"{BASE}/face_detection_yunet/face_detection_yunet_2023mar.onnx",
    "face_recognition_sface_2021dec.onnx": f"{BASE}/face_recognition_sface/face_recognition_sface_2021dec.onnx",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    for name, url in MODELS.items():
        dest = MODELS_DIR / name
        if dest.exists() and dest.stat().st_size > 0:
            print(f"[ok] {name} ya existe")
            continue
        print(f"[..] Descargando {name}")
        try:
            urllib.request.urlretrieve(url, dest)  # noqa: S310
        except Exception as exc:  # noqa: BLE001
            print(f"[error] {name}: {exc}", file=sys.stderr)
            dest.unlink(missing_ok=True)
            return 1
        print(f"[ok] {name} sha256={sha256(dest)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

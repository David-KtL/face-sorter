"""Descarga los modelos ONNX (YuNet y SFace) desde OpenCV Zoo a ./models y verifica su SHA-256."""

from __future__ import annotations

import hashlib
import sys
import urllib.request
from pathlib import Path
from typing import NamedTuple

MODELS_DIR = Path(__file__).resolve().parent.parent / "models"

BASE = "https://github.com/opencv/opencv_zoo/raw/main/models"


class Model(NamedTuple):
    url: str
    sha256: str


MODELS = {
    "face_detection_yunet_2023mar.onnx": Model(
        f"{BASE}/face_detection_yunet/face_detection_yunet_2023mar.onnx",
        "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4",
    ),
    "face_recognition_sface_2021dec.onnx": Model(
        f"{BASE}/face_recognition_sface/face_recognition_sface_2021dec.onnx",
        "0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79",
    ),
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    for name, model in MODELS.items():
        dest = MODELS_DIR / name
        if dest.exists() and sha256(dest) == model.sha256:
            print(f"[ok] {name} ya existe (sha256 verificado)")
            continue
        print(f"[..] Descargando {name}")
        tmp = dest.with_suffix(".part")
        try:
            urllib.request.urlretrieve(model.url, tmp)  # noqa: S310
        except Exception as exc:  # noqa: BLE001
            print(f"[error] {name}: {exc}", file=sys.stderr)
            tmp.unlink(missing_ok=True)
            return 1
        digest = sha256(tmp)
        if digest != model.sha256:
            print(f"[error] {name}: sha256 inesperado {digest}", file=sys.stderr)
            tmp.unlink(missing_ok=True)
            return 1
        tmp.replace(dest)
        print(f"[ok] {name} sha256={digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

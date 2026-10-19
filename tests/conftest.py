"""Shared fixtures. Never commit real photos: images are synthetic or come from LFW in data/."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")  # GUI tests without a screen

from collections.abc import Callable
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from face_sorter.config import HOME_ENV_VAR, PROJECT_ROOT, Settings

LFW_DIR = PROJECT_ROOT / "data" / "lfw"


@pytest.fixture(autouse=True)
def isolated_home(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """Never read or write the real user's settings, cache or logs during tests."""
    home = tmp_path_factory.mktemp("home")
    monkeypatch.setenv(HOME_ENV_VAR, str(home))
    return home


@pytest.fixture(scope="session")
def settings() -> Settings:
    return Settings()


@pytest.fixture(scope="session")
def detector_model(settings: Settings) -> Path:
    path = settings.detector_model_path
    if not path.is_file():
        pytest.skip("Models missing: run python scripts/download_models.py")
    return path


@pytest.fixture(scope="session")
def recognizer_model(settings: Settings) -> Path:
    path = settings.recognizer_model_path
    if not path.is_file():
        pytest.skip("Models missing: run python scripts/download_models.py")
    return path


@pytest.fixture(scope="session")
def lfw_dir() -> Path:
    if not LFW_DIR.is_dir():
        pytest.skip("LFW missing: run python scripts/download_lfw.py")
    return LFW_DIR


@pytest.fixture(scope="session")
def lfw_people(lfw_dir: Path) -> dict[str, list[Path]]:
    """Deterministic subset: the first 12 people (alphabetically) with at least 4 photos."""
    people: dict[str, list[Path]] = {}
    for person in sorted(p for p in lfw_dir.iterdir() if p.is_dir()):
        photos = sorted(person.glob("*.jpg"))
        if len(photos) >= 4:
            people[person.name] = photos[:4]
        if len(people) == 12:
            break
    return people


@pytest.fixture
def make_image(tmp_path: Path) -> Callable[..., Path]:
    """Write a synthetic noise image and return its path."""

    def _make(
        name: str = "img.png", size: tuple[int, int] = (64, 48), mode: str = "RGB", **save: object
    ) -> Path:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        rng = np.random.default_rng(len(name))
        channels = {"RGB": 3, "RGBA": 4, "L": 1}[mode]
        data = rng.integers(0, 256, (size[1], size[0], channels), dtype=np.uint8)
        img = Image.fromarray(data.squeeze() if channels == 1 else data, mode)
        img.save(path, **save)  # type: ignore[arg-type]
        return path

    return _make

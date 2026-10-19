"""Phase 2 acceptance: group purity >= 95 % on a labelled LFW subset (default settings).

The subset mixes 40 people with several photos and 40 people with a single photo
(strangers, who should end up unclassified). Only the labelled (central) face of each
LFW photo is evaluated. Skipped if models or LFW are missing.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from face_sorter.config import Settings
from face_sorter.core.clustering import UNCLASSIFIED, cluster_embeddings, purity
from face_sorter.services.pipeline import FaceInfo, Pipeline

LFW_CENTRE = 125.0


def _central(faces: list[FaceInfo]) -> FaceInfo:
    def dist(f: FaceInfo) -> float:
        x, y, w, h = f.face.bbox
        return abs(x + w / 2 - LFW_CENTRE) + abs(y + h / 2 - LFW_CENTRE)

    return min(faces, key=dist)


@pytest.fixture(scope="module")
def labelled(
    lfw_dir: Path,
    detector_model: Path,
    recognizer_model: Path,
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[list[str], np.ndarray, set[str]]:
    dirs = sorted(p for p in lfw_dir.iterdir() if p.is_dir())
    counts = {p: len(list(p.glob("*.jpg"))) for p in dirs}
    multi = [p for p in dirs if counts[p] >= 6][:40]
    single = [p for p in dirs if counts[p] == 1][:40]
    files = [(p.name, f) for p in multi for f in sorted(p.glob("*.jpg"))[:8]]
    files += [(p.name, next(p.glob("*.jpg"))) for p in single]

    settings = Settings(cache_path=tmp_path_factory.mktemp("cache") / "c.sqlite")
    names: list[str] = []
    embs = []
    with Pipeline(settings) as pipeline:
        for name, f in files:
            usable = [fc for fc in pipeline.process_image(f).faces if fc.usable]
            if usable:
                names.append(name)
                embs.append(_central(usable).embedding)
    return names, np.stack(embs), {p.name for p in multi}


def test_purity_with_default_threshold(labelled: tuple[list[str], np.ndarray, set[str]]) -> None:
    names, x, multi = labelled
    labels = cluster_embeddings(x, Settings().clustering)
    assert purity(labels, names) >= 0.95

    is_multi = np.array([n in multi for n in names])
    # Most photos of known people are grouped, and most strangers stay unclassified.
    assert np.mean(labels[is_multi] != UNCLASSIFIED) >= 0.9
    assert np.mean(labels[~is_multi] == UNCLASSIFIED) >= 0.9
    # A person is rarely split into several groups.
    groups_per_person = [
        len({lb for lb, n in zip(labels, names, strict=True) if n == p and lb != UNCLASSIFIED})
        for p in multi
    ]
    assert np.mean(groups_per_person) <= 1.2

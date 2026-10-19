from __future__ import annotations

import numpy as np
import pytest

from face_sorter.config import ClusteringSettings
from face_sorter.core.clustering import UNCLASSIFIED, cluster_embeddings, purity
from face_sorter.core.embedder import l2_normalize


def _blobs(sizes: list[int], dim: int = 32, noise: float = 0.05, seed: int = 0) -> np.ndarray:
    """Tight groups of unit vectors around random (nearly orthogonal) centres."""
    rng = np.random.default_rng(seed)
    rows = []
    for size in sizes:
        centre = rng.normal(size=dim)
        rows += [l2_normalize(centre + rng.normal(scale=noise * 10, size=dim)) for _ in range(size)]
    return np.stack(rows)


def test_groups_are_found_and_numbered_by_size() -> None:
    x = _blobs([2, 5, 3])
    labels = cluster_embeddings(x)
    # Largest group gets label 0, then 1, then 2.
    assert labels.tolist() == [2, 2, 0, 0, 0, 0, 0, 1, 1, 1]


def test_singletons_are_unclassified() -> None:
    x = _blobs([4, 1, 1])
    labels = cluster_embeddings(x)
    assert labels.tolist() == [0, 0, 0, 0, UNCLASSIFIED, UNCLASSIFIED]


def test_min_cluster_size_is_configurable() -> None:
    x = _blobs([4, 2])
    strict = ClusteringSettings(min_cluster_size=3)
    assert cluster_embeddings(x, strict).tolist() == [0] * 4 + [UNCLASSIFIED] * 2
    keep_all = ClusteringSettings(min_cluster_size=1)
    assert cluster_embeddings(_blobs([1]), keep_all).tolist() == [0]


def test_threshold_controls_merging() -> None:
    x = _blobs([3, 3])
    merged = cluster_embeddings(x, ClusteringSettings(distance_threshold=1.9))
    assert set(merged.tolist()) == {0}


def test_edge_cases() -> None:
    assert cluster_embeddings(np.empty((0, 8))).size == 0
    assert cluster_embeddings(_blobs([1])).tolist() == [UNCLASSIFIED]
    with pytest.raises(ValueError):
        cluster_embeddings(np.zeros(8))


def test_purity() -> None:
    labels = np.array([0, 0, 0, 1, 1, UNCLASSIFIED])
    assert purity(labels, ["a", "a", "b", "c", "c", "z"]) == pytest.approx(4 / 5)
    assert purity(np.array([UNCLASSIFIED]), ["a"]) == 1.0
    with pytest.raises(ValueError):
        purity(labels, ["a"])

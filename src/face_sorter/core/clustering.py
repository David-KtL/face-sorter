"""Group face embeddings by identity (RF-06, ADR 0002)."""

from __future__ import annotations

from collections import Counter

import numpy as np
from numpy.typing import NDArray
from sklearn.cluster import AgglomerativeClustering

from face_sorter.config import ClusteringSettings

UNCLASSIFIED = -1

Labels = NDArray[np.int64]


def cluster_embeddings(
    embeddings: NDArray[np.floating], settings: ClusteringSettings | None = None
) -> Labels:
    """Cluster L2-normalized embeddings (shape ``(n, d)``) by cosine distance.

    Returns one label per row. Groups smaller than ``min_cluster_size`` get
    :data:`UNCLASSIFIED`. Remaining labels are ``0..k-1`` ordered by group size
    (largest first; ties broken by first appearance), so numbering is deterministic.
    """
    s = settings or ClusteringSettings()
    x = np.asarray(embeddings, dtype=np.float64)
    if x.ndim != 2:
        raise ValueError("Expected a 2-D array of embeddings (n, d)")
    n = x.shape[0]
    if n == 0:
        return np.empty(0, dtype=np.int64)
    if n == 1:
        raw = np.zeros(1, dtype=np.int64)
    else:
        model = AgglomerativeClustering(
            n_clusters=None,
            distance_threshold=s.distance_threshold,
            metric="cosine",
            linkage=s.linkage,
        )
        raw = np.asarray(model.fit_predict(x), dtype=np.int64)
    return _relabel(raw, s.min_cluster_size)


def _relabel(raw: Labels, min_size: int) -> Labels:
    sizes = Counter(raw.tolist())
    first_seen: dict[int, int] = {}
    for i, label in enumerate(raw.tolist()):
        first_seen.setdefault(label, i)
    kept = sorted(
        (label for label, size in sizes.items() if size >= min_size),
        key=lambda label: (-sizes[label], first_seen[label]),
    )
    mapping = {old: new for new, old in enumerate(kept)}
    return np.array([mapping.get(label, UNCLASSIFIED) for label in raw.tolist()], dtype=np.int64)


def purity(labels: Labels, truth: list[str]) -> float:
    """Fraction of clustered faces whose group's majority identity is their own.

    Unclassified faces are ignored. Returns 1.0 if nothing was clustered.
    """
    if len(labels) != len(truth):
        raise ValueError("labels and truth must have the same length")
    groups: dict[int, list[str]] = {}
    for label, name in zip(labels.tolist(), truth, strict=True):
        if label != UNCLASSIFIED:
            groups.setdefault(label, []).append(name)
    total = sum(len(g) for g in groups.values())
    if total == 0:
        return 1.0
    majority = sum(Counter(g).most_common(1)[0][1] for g in groups.values())
    return majority / total

"""Small text helpers for user-facing output."""

from __future__ import annotations


def human_size(n: int) -> str:
    """Bytes as text: ``1536`` -> ``1.5 KB``."""
    size = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"  # pragma: no cover

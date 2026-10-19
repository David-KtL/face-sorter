"""CSV report of a plan: photo, group, number of faces (RF-15).

Semicolon-separated and UTF-8 with BOM, so it opens correctly in a Spanish Excel.
A photo placed in several folders (one per person) gets one row per folder.
"""

from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

from face_sorter.config import OUTPUT_MODE_LABELS
from face_sorter.services.plan import OrganizationPlan

CSV_COLUMNS = ["foto", "grupo", "destino", "n_rostros", "estado"]


def plan_rows(plan: OrganizationPlan) -> list[dict[str, str]]:
    """One row per (photo, destination folder), plus unreadable and excluded photos."""
    faces = Counter(f.source for f in plan.faces)
    action = OUTPUT_MODE_LABELS[plan.mode]
    rows = [
        {
            "foto": str(item.source),
            "grupo": item.group,
            "destino": str(item.dest),
            "n_rostros": str(faces[item.source]),
            "estado": action,
        }
        for item in plan.items
    ]
    rows += [
        {
            "foto": str(e.source),
            "grupo": "",
            "destino": "",
            "n_rostros": "0",
            "estado": f"error: {e.error}",
        }
        for e in plan.errors
    ]
    rows += [
        {
            "foto": str(p),
            "grupo": "",
            "destino": "",
            "n_rostros": str(faces[p]),
            "estado": "excluida",
        }
        for p in plan.excluded_images
    ]
    return sorted(rows, key=lambda r: (r["foto"].lower(), r["grupo"]))


def write_csv(plan: OrganizationPlan, path: Path) -> int:
    """Write the report to ``path``. Returns the number of data rows."""
    rows = plan_rows(plan)
    with Path(path).open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, delimiter=";")
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)

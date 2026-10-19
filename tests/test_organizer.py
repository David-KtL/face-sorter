"""Organizer tests: originals untouched (hashes), never overwrite, manifest and undo."""

from __future__ import annotations

import errno
import json
import os
from collections.abc import Callable
from pathlib import Path, PurePosixPath

import pytest

from face_sorter.config import OutputMode
from face_sorter.core.image_io import sha256_file
from face_sorter.services import organizer as org
from face_sorter.services.organizer import (
    EntryResult,
    Manifest,
    Method,
    OrganizerError,
    RemovalState,
    RunStatus,
    apply_plan,
    undo,
)
from face_sorter.services.plan import OrganizationPlan, PlanItem

Snapshot = dict[str, str]


def snapshot(root: Path) -> Snapshot:
    """Relative path -> SHA-256 of every file under ``root`` (manifests excluded)."""
    if not root.exists():
        return {}
    return {
        p.relative_to(root).as_posix(): sha256_file(p)
        for p in sorted(root.rglob("*"))
        if p.is_file() and not p.name.startswith("manifest_")
    }


def dirs(root: Path) -> list[str]:
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_dir())


@pytest.fixture
def src(tmp_path: Path) -> Path:
    root = tmp_path / "photos"
    (root / "sub").mkdir(parents=True)
    for name, content in {
        "a.jpg": b"photo A" * 100,
        "b.jpg": b"photo B" * 100,
        "sub/a.jpg": b"another A" * 100,  # same name, different photo
        "group.jpg": b"two people" * 100,
    }.items():
        (root / name).write_bytes(content)
    return root


@pytest.fixture
def make_plan(src: Path, tmp_path: Path) -> Callable[..., OrganizationPlan]:
    def _make(mode: OutputMode = OutputMode.COPY, out: Path | None = None) -> OrganizationPlan:
        items = [
            ("a.jpg", "Persona_001/a.jpg"),
            ("sub/a.jpg", "Persona_001/a (2).jpg"),
            ("group.jpg", "Persona_001/group.jpg"),
            ("group.jpg", "Persona_002/group.jpg"),  # RF-07: one photo, two folders
            ("b.jpg", "_sin_clasificar/b.jpg"),
        ]
        plan_items = [PlanItem(src / s, PurePosixPath(d), d.split("/")[0]) for s, d in items]
        return OrganizationPlan(src, out or tmp_path / "out", mode, [], plan_items, [], [])

    return _make


# -- copy --------------------------------------------------------------------------------


def test_copy_creates_verified_copies_and_keeps_originals(
    src: Path, make_plan: Callable[..., OrganizationPlan]
) -> None:
    before = snapshot(src)
    plan = make_plan()
    result = apply_plan(plan)
    out = plan.output_root

    assert snapshot(src) == before  # golden rule
    assert snapshot(out) == {
        "Persona_001/a.jpg": before["a.jpg"],
        "Persona_001/a (2).jpg": before["sub/a.jpg"],
        "Persona_001/group.jpg": before["group.jpg"],
        "Persona_002/group.jpg": before["group.jpg"],
        "_sin_clasificar/b.jpg": before["b.jpg"],
    }
    assert result.manifest.status is RunStatus.COMPLETED
    assert result.count(EntryResult.CREATED) == 5
    assert result.manifest_path.parent == out.resolve()
    assert result.manifest_path.name.startswith("manifest_")
    saved = Manifest.load(result.manifest_path)
    assert [e.dest for e in saved.entries] == [e.dest for e in result.manifest.entries]
    assert "Creados: 5" in result.summary()


def test_undo_restores_previous_state(
    src: Path, make_plan: Callable[..., OrganizationPlan]
) -> None:
    before = snapshot(src)
    plan = make_plan()
    result = apply_plan(plan)

    preview = undo(result.manifest_path, dry_run=True)
    assert len(preview.deleted) == 5 and "restaurarían" in preview.summary()
    assert len(snapshot(plan.output_root)) == 5  # dry-run changed nothing

    report = undo(result.manifest_path)
    assert len(report.deleted) == 5 and not report.errors
    assert snapshot(plan.output_root) == {}
    assert dirs(plan.output_root) == []  # created folders removed
    assert snapshot(src) == before
    assert Manifest.load(result.manifest_path).status is RunStatus.UNDONE
    assert undo(result.manifest_path).already_undone


def test_existing_identical_file_is_skipped_and_kept_on_undo(
    src: Path, make_plan: Callable[..., OrganizationPlan]
) -> None:
    plan = make_plan()
    existing = plan.output_root / "Persona_001" / "a.jpg"
    existing.parent.mkdir(parents=True)
    existing.write_bytes((src / "a.jpg").read_bytes())

    result = apply_plan(plan)
    assert result.count(EntryResult.SKIPPED_IDENTICAL) == 1
    undo(result.manifest_path)
    assert existing.read_bytes() == (src / "a.jpg").read_bytes()  # not ours: kept


def test_never_overwrites_a_different_file(
    src: Path, make_plan: Callable[..., OrganizationPlan]
) -> None:
    plan = make_plan()
    existing = plan.output_root / "_sin_clasificar" / "b.jpg"
    existing.parent.mkdir(parents=True)
    existing.write_bytes(b"user's own file")

    result = apply_plan(plan)
    assert existing.read_bytes() == b"user's own file"
    renamed = plan.output_root / "_sin_clasificar" / "b (2).jpg"
    assert renamed.read_bytes() == (src / "b.jpg").read_bytes()
    assert any(e.dest == str(renamed) for e in result.manifest.entries)

    undo(result.manifest_path)
    assert existing.read_bytes() == b"user's own file"
    assert not renamed.exists()
    assert (plan.output_root / "_sin_clasificar").is_dir()  # not empty: kept


def test_undo_keeps_files_modified_after_the_run(
    src: Path, make_plan: Callable[..., OrganizationPlan]
) -> None:
    plan = make_plan()
    result = apply_plan(plan)
    edited = plan.output_root / "Persona_002" / "group.jpg"
    edited.write_bytes(b"edited by the user")

    report = undo(result.manifest_path)
    assert report.kept_modified == [str(edited)]
    assert edited.read_bytes() == b"edited by the user"
    assert "modificados" in report.summary()


def test_undo_reports_files_already_gone(
    src: Path, make_plan: Callable[..., OrganizationPlan]
) -> None:
    plan = make_plan()
    result = apply_plan(plan)
    (plan.output_root / "_sin_clasificar" / "b.jpg").unlink()
    report = undo(result.manifest_path)
    assert len(report.missing) == 1 and len(report.deleted) == 4


def test_missing_source_fails_only_that_item(
    src: Path, make_plan: Callable[..., OrganizationPlan]
) -> None:
    plan = make_plan()
    (src / "b.jpg").unlink()
    result = apply_plan(plan)
    assert result.count(EntryResult.FAILED) == 1
    assert result.count(EntryResult.CREATED) == 4
    assert "FALLÓ" in result.summary()


# -- preflight ---------------------------------------------------------------------------


def test_output_equal_to_source_is_refused(
    src: Path, make_plan: Callable[..., OrganizationPlan]
) -> None:
    before = snapshot(src)
    with pytest.raises(OrganizerError, match="distinta"):
        apply_plan(make_plan(out=src))
    assert snapshot(src) == before


def test_destination_escaping_output_is_refused(
    src: Path, tmp_path: Path, make_plan: Callable[..., OrganizationPlan]
) -> None:
    plan = make_plan()
    plan.items.append(PlanItem(src / "a.jpg", PurePosixPath("../evil.jpg"), "x"))
    with pytest.raises(OrganizerError, match="fuera"):
        apply_plan(plan)
    assert not plan.output_root.exists()
    assert not (tmp_path / "evil.jpg").exists()


def test_not_enough_space_is_refused(
    make_plan: Callable[..., OrganizationPlan], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(org.shutil, "disk_usage", lambda p: type("U", (), {"free": 10})())
    plan = make_plan()
    with pytest.raises(OrganizerError, match="espacio suficiente"):
        apply_plan(plan)
    assert not plan.output_root.exists()


# -- cancel / interrupt --------------------------------------------------------------------


def test_cancel_stops_and_is_undoable(make_plan: Callable[..., OrganizationPlan]) -> None:
    plan = make_plan()
    calls: list[int] = []
    result = apply_plan(plan, progress=lambda d, t: calls.append(d), cancel=lambda: len(calls) >= 2)
    assert result.manifest.status is RunStatus.CANCELLED
    assert len(result.manifest.entries) == 2
    undo(result.manifest_path)
    assert snapshot(plan.output_root) == {}


def test_interrupted_run_is_still_undoable(make_plan: Callable[..., OrganizationPlan]) -> None:
    plan = make_plan()

    def boom(done: int, total: int) -> None:
        if done == 3:
            raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        apply_plan(plan, progress=boom)
    manifest_path = next(plan.output_root.glob("manifest_*.json"))
    assert Manifest.load(manifest_path).status is RunStatus.IN_PROGRESS
    undo(manifest_path)
    assert snapshot(plan.output_root) == {}


# -- hardlink ------------------------------------------------------------------------------


def test_hardlink_mode(src: Path, make_plan: Callable[..., OrganizationPlan]) -> None:
    before = snapshot(src)
    plan = make_plan(OutputMode.HARDLINK)
    result = apply_plan(plan)
    assert all(e.method is Method.LINK for e in result.manifest.entries)
    assert os.path.samefile(plan.output_root / "Persona_001" / "a.jpg", src / "a.jpg")
    assert result.fallbacks == 0

    undo(result.manifest_path)
    assert snapshot(plan.output_root) == {}
    assert snapshot(src) == before  # deleting links never touches the originals


def test_hardlink_falls_back_to_copy_on_another_drive(
    src: Path, make_plan: Callable[..., OrganizationPlan], monkeypatch: pytest.MonkeyPatch
) -> None:
    def no_link(a: object, b: object) -> None:
        raise OSError(errno.EXDEV, "Invalid cross-device link")

    monkeypatch.setattr(org.os, "link", no_link)
    result = apply_plan(make_plan(OutputMode.HARDLINK))
    assert result.count(EntryResult.CREATED) == 5
    assert result.fallbacks == 5
    assert "se copiaron" in result.summary()


# -- move ----------------------------------------------------------------------------------


def test_move_requires_confirmation(make_plan: Callable[..., OrganizationPlan]) -> None:
    plan = make_plan(OutputMode.MOVE)
    with pytest.raises(OrganizerError, match="confirmación"):
        apply_plan(plan)
    assert not plan.output_root.exists()


@pytest.mark.parametrize("same_drive", [True, False])
def test_move_and_undo(
    src: Path,
    make_plan: Callable[..., OrganizationPlan],
    monkeypatch: pytest.MonkeyPatch,
    same_drive: bool,
) -> None:
    if not same_drive:
        monkeypatch.setattr(
            org.os, "link", lambda a, b: (_ for _ in ()).throw(OSError(errno.EXDEV, "xdev"))
        )
    before = snapshot(src)
    plan = make_plan(OutputMode.MOVE)
    result = apply_plan(plan, confirm_move=True)

    assert snapshot(src) == {}  # all originals moved out
    out = snapshot(plan.output_root)
    assert out["Persona_001/group.jpg"] == out["Persona_002/group.jpg"] == before["group.jpg"]
    assert all(r.state is RemovalState.DONE for r in result.manifest.removals)
    assert "Originales movidos: 4" in result.summary()

    report = undo(result.manifest_path)
    assert sorted(report.restored) == sorted(str(src / p) for p in before)
    assert snapshot(src) == before
    assert snapshot(plan.output_root) == {}


def test_move_keeps_original_if_any_copy_failed(
    src: Path, make_plan: Callable[..., OrganizationPlan], monkeypatch: pytest.MonkeyPatch
) -> None:
    real_link = os.link

    def flaky_link(a: str | Path, b: str | Path) -> None:
        if "Persona_002" in str(b):
            raise PermissionError(errno.EACCES, "denied")
        real_link(a, b)

    monkeypatch.setattr(org.os, "link", flaky_link)
    result = apply_plan(make_plan(OutputMode.MOVE), confirm_move=True)
    assert (src / "group.jpg").exists()  # one of its two copies failed
    assert not (src / "a.jpg").exists()
    states = {Path(r.source).name: r.state for r in result.manifest.removals}
    assert states["group.jpg"] is RemovalState.KEPT


def test_move_keeps_original_changed_during_run(
    src: Path, make_plan: Callable[..., OrganizationPlan]
) -> None:
    plan = make_plan(OutputMode.MOVE)
    organizer = org.Organizer(plan)
    original_remove = organizer._remove_moved_sources

    def change_then_remove(manifest: Manifest, path: Path) -> None:
        (src / "b.jpg").write_bytes(b"changed")  # breaks the hard link content too
        original_remove(manifest, path)

    organizer._remove_moved_sources = change_then_remove  # type: ignore[method-assign]
    organizer.apply(confirm_move=True)
    assert (src / "b.jpg").read_bytes() == b"changed"


def test_move_cancelled_keeps_all_originals(
    src: Path, make_plan: Callable[..., OrganizationPlan]
) -> None:
    before = snapshot(src)
    result = apply_plan(make_plan(OutputMode.MOVE), confirm_move=True, cancel=lambda: True)
    assert snapshot(src) == before
    assert result.manifest.status is RunStatus.CANCELLED


def test_undo_restores_from_preexisting_identical_copy(
    src: Path, make_plan: Callable[..., OrganizationPlan]
) -> None:
    plan = make_plan(OutputMode.MOVE)
    plan.items[:] = [plan.items[-1]]  # only b.jpg
    existing = plan.output_root / "_sin_clasificar" / "b.jpg"
    existing.parent.mkdir(parents=True)
    existing.write_bytes((src / "b.jpg").read_bytes())
    content = existing.read_bytes()

    result = apply_plan(plan, confirm_move=True)
    assert not (src / "b.jpg").exists()
    undo(result.manifest_path)
    assert (src / "b.jpg").read_bytes() == content
    assert existing.read_bytes() == content  # the user's file stays


def test_undo_cannot_restore_without_intact_copy(
    src: Path, make_plan: Callable[..., OrganizationPlan]
) -> None:
    plan = make_plan(OutputMode.MOVE)
    plan.items[:] = [plan.items[-1]]
    result = apply_plan(plan, confirm_move=True)
    (plan.output_root / "_sin_clasificar" / "b.jpg").write_bytes(b"tampered")
    report = undo(result.manifest_path)
    assert report.errors and "ninguna copia intacta" in report.errors[0]


# -- manifest ------------------------------------------------------------------------------


def test_manifest_errors(tmp_path: Path) -> None:
    bad = tmp_path / "manifest_bad.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(OrganizerError, match="No se puede leer"):
        undo(bad)
    bad.write_text(json.dumps({"format_version": 99}), encoding="utf-8")
    with pytest.raises(OrganizerError, match="no soportada"):
        undo(bad)


# -- failures while copying -------------------------------------------------------------


def test_disk_full_leaves_no_partial_file(
    src: Path, make_plan: Callable[..., OrganizationPlan], monkeypatch: pytest.MonkeyPatch
) -> None:
    def disk_full(fin: object, fout: object, length: int = 0) -> None:
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(org.shutil, "copyfileobj", disk_full)
    plan = make_plan()
    result = apply_plan(plan)
    assert result.count(EntryResult.FAILED) == 5
    assert snapshot(plan.output_root) == {}  # partial files removed


def test_corrupted_copy_is_detected_and_removed(
    src: Path, make_plan: Callable[..., OrganizationPlan], monkeypatch: pytest.MonkeyPatch
) -> None:
    real = org.sha256_file

    def lying_hash(path: Path) -> str:
        return "0" * 64 if "out" in Path(path).parts else real(path)

    monkeypatch.setattr(org, "sha256_file", lying_hash)
    plan = make_plan()
    result = apply_plan(plan)
    assert result.count(EntryResult.FAILED) == 5
    assert all("La verificación falló" in (e.error or "") for e in result.manifest.entries)
    assert snapshot(plan.output_root) == {}

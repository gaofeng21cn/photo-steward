import json
import os
import sqlite3
from pathlib import Path

import tools.icloud_photo_sync.runtime as runtime
from tools.icloud_photo_sync.models import ICloudResource, NasFile
from tools.icloud_photo_sync.planner import build_sync_plan
from tools.icloud_photo_sync.runtime import persist_plan_bundle, run_apply
from tools.icloud_photo_sync.state import StateStore


def test_persist_plan_bundle_writes_expected_files(tmp_path: Path) -> None:
    resources = [
        ICloudResource(
            resource_key="asset-1:0:IMG_0001.JPG",
            asset_uuid="asset-1",
            asset_local_identifier="asset-1/L0/001",
            resource_index=0,
            original_filename="IMG_0001.JPG",
            created_at="2024-10-10T10:00:00+08:00",
            sha256="sha-a",
            bytes_count=100,
            source_kind="local_file",
            source_path="/source/IMG_0001.JPG",
            source_state_token="src-1",
        )
    ]
    nas_files = [
        NasFile(
            relative_path="2024/10/EXTRA.JPG",
            absolute_path="/nas/2024/10/EXTRA.JPG",
            sha256="sha-x",
            bytes_count=50,
            state_token="nas-1",
        )
    ]
    plan = build_sync_plan(resources, nas_files, {}, "plan-1")
    plan_dir = tmp_path / "plan-1"

    persist_plan_bundle(
        plan_dir=plan_dir,
        plan=plan,
        icloud_resources=resources,
        nas_files=nas_files,
        unresolved=[{"kind": "sample"}],
    )

    assert (plan_dir / "plan_summary.json").exists()
    assert (plan_dir / "present_in_icloud_manifest.jsonl").exists()
    assert (plan_dir / "present_in_nas_manifest.jsonl").exists()
    assert (plan_dir / "mirror_to_nas.json").exists()
    assert (plan_dir / "move_to_nas_deleted_pool.json").exists()
    assert (plan_dir / "unresolved.json").exists()
    assert (plan_dir / "proposed_bindings.json").exists()

    summary = json.loads((plan_dir / "plan_summary.json").read_text(encoding="utf-8"))
    assert summary["plan_id"] == "plan-1"
    assert summary["mirror_count"] == 1
    assert summary["mirror_bytes"] == 100
    assert summary["delete_count"] == 1
    assert summary["delete_bytes"] == 50
    assert summary["unresolved_count"] == 1


def test_iter_nas_files_fails_closed_on_walk_error(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "Photos"

    class Fingerprinter:
        def fingerprint_path(self, source_kind, resource_key, path):
            raise AssertionError("fingerprinter should not run")

    def failing_walk(path, onerror=None):
        assert onerror is not None
        onerror(PermissionError(13, "Permission denied", os.fspath(path)))
        yield from ()

    monkeypatch.setattr(runtime.os, "walk", failing_walk)
    try:
        runtime._iter_nas_files(root, Fingerprinter())
    except RuntimeError as exc:
        assert "NAS scan failed" in str(exc)
        assert "Permission denied" in str(exc)
    else:
        raise AssertionError("expected NAS scan failure")


def _prepare_apply_state(tmp_path: Path) -> tuple[Path, Path]:
    plan_dir = tmp_path / "plan-apply"
    plan_dir.mkdir()
    (plan_dir / "proposed_bindings.json").write_text(
        json.dumps(
            {
                "plan_id": "plan-apply",
                "bindings": {"asset-1:0:IMG.JPG": "2025/09/IMG.JPG"},
            }
        ),
        encoding="utf-8",
    )
    state_db = tmp_path / "state.sqlite3"
    store = StateStore(state_db)
    store.record_plan("plan-apply", str(plan_dir), "{}")
    store.close()
    return plan_dir, state_db


def test_run_apply_commits_bindings_only_after_success(tmp_path: Path, monkeypatch) -> None:
    plan_dir, state_db = _prepare_apply_state(tmp_path)

    def fake_execute_apply(**kwargs):
        receipt = {"plan_id": "plan-apply", "status": "success"}
        (plan_dir / "apply_receipt.json").write_text(json.dumps(receipt), encoding="utf-8")
        return receipt

    monkeypatch.setattr(runtime, "execute_apply", fake_execute_apply)
    run_apply(
        plan_dir=plan_dir,
        nas_root=tmp_path / "Photos",
        deleted_root=tmp_path / "Deleted",
        state_db=state_db,
        swift_source=tmp_path / "bridge.swift",
    )

    store = StateStore(state_db)
    assert store.get_binding("asset-1:0:IMG.JPG") == "2025/09/IMG.JPG"
    store.close()
    with sqlite3.connect(state_db) as connection:
        assert connection.execute(
            "SELECT applied_at FROM plan_runs WHERE plan_id = 'plan-apply'"
        ).fetchone()[0] is not None


def test_run_apply_leaves_bindings_pending_after_partial_receipt(tmp_path: Path, monkeypatch) -> None:
    plan_dir, state_db = _prepare_apply_state(tmp_path)

    def fake_execute_apply(**kwargs):
        receipt = {"plan_id": "plan-apply", "status": "partial"}
        (plan_dir / "apply_receipt.json").write_text(json.dumps(receipt), encoding="utf-8")
        return receipt

    monkeypatch.setattr(runtime, "execute_apply", fake_execute_apply)
    run_apply(
        plan_dir=plan_dir,
        nas_root=tmp_path / "Photos",
        deleted_root=tmp_path / "Deleted",
        state_db=state_db,
        swift_source=tmp_path / "bridge.swift",
    )

    store = StateStore(state_db)
    assert store.get_binding("asset-1:0:IMG.JPG") is None
    store.close()
    with sqlite3.connect(state_db) as connection:
        assert connection.execute(
            "SELECT applied_at FROM plan_runs WHERE plan_id = 'plan-apply'"
        ).fetchone()[0] is None

from __future__ import annotations

import importlib.util
import json
from datetime import date
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "scripts/nas/photo_steward_nas_worker.py"
SPEC = importlib.util.spec_from_file_location("photo_steward_nas_worker", MODULE_PATH)
assert SPEC and SPEC.loader
nas_worker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(nas_worker)


def test_dated_candidates_selects_only_expired_date_directories(tmp_path: Path) -> None:
    root = tmp_path / "Photos_DeletedFromICloud"
    for name in ("2026-06-01", "2026-07-20", "not-a-date"):
        (root / name).mkdir(parents=True)

    candidates = nas_worker.dated_candidates(root, 30, date(2026, 8, 3))

    assert [candidate.name for candidate in candidates] == ["2026-06-01"]


def test_rsync_dry_run_does_not_create_a_missing_target(tmp_path: Path) -> None:
    source = tmp_path / "Photos"
    target = tmp_path / "OneDrive/Photos"
    source.mkdir()

    result = nas_worker.rsync_tree(source, target, True, "/usr/bin/rsync")

    assert result["status"] == "missing_target"
    assert not target.exists()


def test_default_retention_is_audit_only(tmp_path: Path, monkeypatch) -> None:
    nas_home = tmp_path / "home"
    onedrive_root = nas_home / "OneDrive/Backup/icloud-photo-sync"
    for relative in (
        "Photos",
        "Photos_DeletedFromICloud/2026-06-01",
        "Photos_SyncLogs",
        "OneDrive/Backup/icloud-photo-sync/Photos",
        "OneDrive/Backup/icloud-photo-sync/Photos_DeletedFromICloud",
        "OneDrive/Backup/icloud-photo-sync/Photos_SyncLogs",
    ):
        (nas_home / relative).mkdir(parents=True)

    def successful_rsync(source, target, dry_run, rsync_bin):
        return {
            "source": str(source),
            "target": str(target),
            "status": "success",
            "exit_code": 0,
            "command": [rsync_bin],
            "stderr": "",
        }

    monkeypatch.setattr(nas_worker, "rsync_tree", successful_rsync)
    monkeypatch.setattr(
        "sys.argv",
        [
            str(MODULE_PATH),
            "--nas-home",
            str(nas_home),
            "--onedrive-root",
            str(onedrive_root),
            "--today",
            "2026-08-03",
        ],
    )

    assert nas_worker.main() == 0
    assert (nas_home / "Photos_DeletedFromICloud/2026-06-01").is_dir()
    receipts = sorted((nas_home / "Photos_SyncLogs/2026-08-03").glob("nas-maintenance-*.json"))
    payload = json.loads(receipts[-1].read_text(encoding="utf-8"))
    assert payload["retention"]["status"] == "audit_only"
    assert payload["retention"]["candidate_roots"] == ["2026-06-01"]
    assert payload["retention"]["deleted_roots"] == []
    assert payload["worker_sha256"]


def test_apply_retention_dry_run_never_deletes(tmp_path: Path, monkeypatch) -> None:
    nas_home = tmp_path / "home"
    expired = nas_home / "Photos_DeletedFromICloud/2026-06-01"
    for relative in (
        "Photos",
        "Photos_SyncLogs",
        "OneDrive/Backup/icloud-photo-sync/Photos",
        "OneDrive/Backup/icloud-photo-sync/Photos_DeletedFromICloud",
        "OneDrive/Backup/icloud-photo-sync/Photos_SyncLogs",
    ):
        (nas_home / relative).mkdir(parents=True)
    expired.mkdir(parents=True)

    monkeypatch.setattr(
        nas_worker,
        "rsync_tree",
        lambda source, target, dry_run, rsync_bin: {
            "source": str(source),
            "target": str(target),
            "status": "success",
            "exit_code": 0,
        },
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            str(MODULE_PATH),
            "--nas-home",
            str(nas_home),
            "--today",
            "2026-08-03",
            "--apply-retention",
            "--dry-run",
        ],
    )

    assert nas_worker.main() == 0
    assert expired.is_dir()
    receipts = sorted((nas_home / "Photos_SyncLogs/2026-08-03").glob("nas-maintenance-*.json"))
    payload = json.loads(receipts[-1].read_text(encoding="utf-8"))
    assert payload["retention"]["status"] == "dry_run"
    assert payload["retention"]["deleted_roots"] == []

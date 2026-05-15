import json
import subprocess
from pathlib import Path

from tools.icloud_photo_sync.onedrive import default_backup_jobs, run_onedrive_backup


def test_default_backup_jobs_cover_photos_deleted_pool_and_logs(tmp_path: Path) -> None:
    jobs = default_backup_jobs(
        nas_root=tmp_path / "Photos",
        deleted_root=tmp_path / "Photos_DeletedFromICloud",
        logs_root=tmp_path / "Photos_SyncLogs",
        onedrive_root=tmp_path / "OneDriveBackup",
    )

    assert [job.name for job in jobs] == ["photos", "deleted_pool", "sync_logs"]
    assert jobs[0].target_root == tmp_path / "OneDriveBackup" / "Photos"
    assert jobs[1].target_root == tmp_path / "OneDriveBackup" / "Photos_DeletedFromICloud"
    assert jobs[2].target_root == tmp_path / "OneDriveBackup" / "Photos_SyncLogs"


def test_run_onedrive_backup_writes_receipt_and_uses_rsync_without_delete(tmp_path: Path) -> None:
    source_root = tmp_path / "Photos"
    source_root.mkdir()
    target_root = tmp_path / "OneDriveBackup"
    logs_root = tmp_path / "Photos_SyncLogs"
    commands: list[list[str]] = []

    def fake_runner(command, capture_output, text, check):
        commands.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    receipt_path = run_onedrive_backup(
        jobs=default_backup_jobs(
            nas_root=source_root,
            deleted_root=tmp_path / "Deleted",
            logs_root=logs_root,
            onedrive_root=target_root,
        ),
        logs_root=logs_root,
        job_id="backup-1",
        command_runner=fake_runner,
    )

    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["job_id"] == "backup-1"
    assert receipt["job_count"] == 3
    assert all("--delete" not in command for command in commands)

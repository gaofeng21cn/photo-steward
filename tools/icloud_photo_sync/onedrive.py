from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable


@dataclass(frozen=True)
class BackupJob:
    name: str
    source_root: Path
    target_root: Path


def default_backup_jobs(
    *,
    nas_root: Path,
    deleted_root: Path,
    logs_root: Path,
    onedrive_root: Path,
) -> list[BackupJob]:
    onedrive_root = Path(onedrive_root)
    return [
        BackupJob(name="photos", source_root=Path(nas_root), target_root=onedrive_root / "Photos"),
        BackupJob(
            name="deleted_pool",
            source_root=Path(deleted_root),
            target_root=onedrive_root / "Photos_DeletedFromICloud",
        ),
        BackupJob(name="sync_logs", source_root=Path(logs_root), target_root=onedrive_root / "Photos_SyncLogs"),
    ]


def run_onedrive_backup(
    *,
    nas_root: Path | None = None,
    deleted_root: Path | None = None,
    logs_root: Path,
    onedrive_root: Path | None = None,
    job_id: str | None = None,
    dry_run: bool = False,
    jobs: list[BackupJob] | None = None,
    command_runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    rsync_bin: str = "/usr/bin/rsync",
) -> Path:
    now = datetime.now().astimezone()
    job_id = job_id or now.strftime("onedrive-backup-%Y%m%dT%H%M%S")
    if jobs is None:
        if nas_root is None or deleted_root is None or onedrive_root is None:
            raise ValueError("nas_root、deleted_root、onedrive_root 必须提供，或直接传入 jobs")
        jobs = default_backup_jobs(
            nas_root=nas_root,
            deleted_root=deleted_root,
            logs_root=logs_root,
            onedrive_root=onedrive_root,
        )

    results: list[dict] = []
    status = "success"
    for job in jobs:
        if not job.source_root.exists():
            results.append(
                {
                    "name": job.name,
                    "source_root": str(job.source_root),
                    "target_root": str(job.target_root),
                    "status": "missing_source",
                    "exit_code": 0,
                    "command": [],
                }
            )
            continue

        job.target_root.mkdir(parents=True, exist_ok=True)
        command = [
            rsync_bin,
            "-a",
            "--exclude=.DS_Store",
        ]
        if dry_run:
            command.append("--dry-run")
        command.extend([f"{job.source_root}/", f"{job.target_root}/"])
        proc = command_runner(command, capture_output=True, text=True, check=False)
        job_status = "success" if proc.returncode == 0 else "failed"
        if proc.returncode != 0:
            status = "failed"
        results.append(
            {
                "name": job.name,
                "source_root": str(job.source_root),
                "target_root": str(job.target_root),
                "status": job_status,
                "exit_code": proc.returncode,
                "command": command,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
            }
        )

    payload = {
        "job_id": job_id,
        "status": status,
        "started_at": now.isoformat(),
        "finished_at": datetime.now().astimezone().isoformat(),
        "dry_run": dry_run,
        "job_count": len(jobs),
        "results": results,
    }
    receipt_dir = Path(logs_root) / now.strftime("%Y-%m-%d")
    receipt_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = receipt_dir / f"{job_id}.json"
    receipt_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return receipt_path

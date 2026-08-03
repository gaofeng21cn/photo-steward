#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Photo Steward NAS-side maintenance.")
    parser.add_argument("--nas-home", type=Path, default=Path.home())
    parser.add_argument("--onedrive-root", type=Path)
    parser.add_argument("--retention-days", type=int, default=30)
    parser.add_argument("--apply-retention", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--today", type=date.fromisoformat)
    parser.add_argument("--rsync-bin", default="/usr/bin/rsync")
    return parser.parse_args()


def dated_candidates(root: Path, retention_days: int, today: date) -> list[Path]:
    cutoff = today - timedelta(days=retention_days)
    candidates: list[Path] = []
    if not root.exists():
        return candidates
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        try:
            parsed = date.fromisoformat(child.name)
        except ValueError:
            continue
        if parsed < cutoff:
            candidates.append(child)
    return candidates


def rsync_tree(source: Path, target: Path, dry_run: bool, rsync_bin: str) -> dict[str, object]:
    if not source.is_dir():
        return {
            "source": str(source),
            "target": str(target),
            "status": "missing_source",
            "exit_code": 66,
        }

    if dry_run and not target.is_dir():
        return {
            "source": str(source),
            "target": str(target),
            "status": "missing_target",
            "exit_code": 66,
        }
    target.mkdir(parents=True, exist_ok=True)
    command = [rsync_bin, "-a", "--exclude=.DS_Store"]
    if dry_run:
        command.append("--dry-run")
    command.extend([f"{source}/", f"{target}/"])
    proc = subprocess.run(command, capture_output=True, text=True, check=False)
    return {
        "source": str(source),
        "target": str(target),
        "status": "success" if proc.returncode == 0 else "failed",
        "exit_code": proc.returncode,
        "command": command,
        "stderr": proc.stderr,
    }


def main() -> int:
    args = parse_args()
    now = datetime.now(timezone.utc).astimezone()
    today = args.today or now.date()
    nas_home = args.nas_home.expanduser().resolve()
    onedrive_root = (args.onedrive_root or nas_home / "OneDrive/Backup/icloud-photo-sync").expanduser().resolve()
    photos_root = nas_home / "Photos"
    quarantine_root = nas_home / "Photos_DeletedFromICloud"
    receipts_root = nas_home / "Photos_SyncLogs"

    backup_results = [
        rsync_tree(photos_root, onedrive_root / "Photos", args.dry_run, args.rsync_bin),
        rsync_tree(quarantine_root, onedrive_root / "Photos_DeletedFromICloud", args.dry_run, args.rsync_bin),
        rsync_tree(receipts_root, onedrive_root / "Photos_SyncLogs", args.dry_run, args.rsync_bin),
    ]
    backup_status = "success" if all(item["exit_code"] == 0 for item in backup_results) else "failed"

    candidates = dated_candidates(quarantine_root, args.retention_days, today)
    deleted: list[str] = []
    retention_errors: list[dict[str, str]] = []
    retention_status = "audit_only"
    if args.apply_retention:
        retention_status = "dry_run" if args.dry_run else "success"
        if not args.dry_run:
            for candidate in candidates:
                try:
                    shutil.rmtree(candidate)
                    deleted.append(candidate.name)
                except OSError as exc:
                    retention_errors.append({"root": candidate.name, "error": str(exc)})
            if retention_errors:
                retention_status = "failed"

    overall_status = "success" if backup_status == "success" and not retention_errors else "failed"

    receipt = {
        "schema_version": 1,
        "job_id": now.strftime("nas-maintenance-%Y%m%dT%H%M%S%z"),
        "started_at": now.isoformat(),
        "finished_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "status": overall_status,
        "authority": "icloud_photos",
        "nas_role": "mirror",
        "onedrive_role": "off_site_backup",
        "worker_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "dry_run": args.dry_run,
        "backup": {
            "status": backup_status,
            "results": backup_results,
        },
        "retention": {
            "status": retention_status,
            "retention_days": args.retention_days,
            "candidate_roots": [candidate.name for candidate in candidates],
            "deleted_roots": deleted,
            "errors": retention_errors,
        },
    }

    receipt_dir = receipts_root / today.isoformat()
    receipt_path = receipt_dir / f"{receipt['job_id']}.json"
    try:
        receipt_dir.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        print(f"cannot write NAS receipt {receipt_path}: {exc}", file=sys.stderr)
        return 1
    print(receipt_path)
    return 0 if overall_status == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())

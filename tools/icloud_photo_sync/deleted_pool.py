from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path


@dataclass(frozen=True)
class DeletedPoolCandidate:
    relative_root: str
    absolute_path: Path


def _parse_date_dir(name: str) -> date | None:
    try:
        return date.fromisoformat(name)
    except ValueError:
        return None


def plan_deleted_pool_prune(
    *,
    deleted_root: Path,
    retention_days: int,
    today: date | None = None,
) -> list[DeletedPoolCandidate]:
    deleted_root = Path(deleted_root)
    today = today or date.today()
    cutoff = today - timedelta(days=retention_days)
    candidates: list[DeletedPoolCandidate] = []
    if not deleted_root.exists():
        return candidates

    for child in sorted(deleted_root.iterdir()):
        if not child.is_dir():
            continue
        parsed = _parse_date_dir(child.name)
        if parsed is None:
            continue
        if parsed < cutoff:
            candidates.append(DeletedPoolCandidate(relative_root=child.name, absolute_path=child))
    return candidates


def prune_deleted_pool(
    *,
    deleted_root: Path,
    logs_root: Path,
    retention_days: int,
    today: date | None = None,
    job_id: str | None = None,
    dry_run: bool = False,
) -> Path:
    today = today or date.today()
    job_id = job_id or datetime.now().astimezone().strftime("deleted-pool-prune-%Y%m%dT%H%M%S")
    candidates = plan_deleted_pool_prune(
        deleted_root=deleted_root,
        retention_days=retention_days,
        today=today,
    )

    deleted_roots: list[str] = []
    if not dry_run:
        for candidate in candidates:
            shutil.rmtree(candidate.absolute_path)
            deleted_roots.append(candidate.relative_root)

    payload = {
        "job_id": job_id,
        "status": "success",
        "retention_days": retention_days,
        "today": today.isoformat(),
        "dry_run": dry_run,
        "candidate_roots": [candidate.relative_root for candidate in candidates],
        "deleted_roots": deleted_roots,
    }

    receipt_dir = Path(logs_root) / today.isoformat()
    receipt_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = receipt_dir / f"{job_id}.json"
    receipt_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return receipt_path

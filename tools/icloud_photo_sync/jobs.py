from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Callable

from .deleted_pool import prune_deleted_pool
from .folder_sync import plan_folder_sync
from .onedrive import run_onedrive_backup
from .runtime import run_apply, run_plan


def _json_dumps(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _status_path(status_dir: Path, job_name: str) -> Path:
    return status_dir / f"latest_{job_name}.json"


def _overview_path(status_dir: Path) -> Path:
    return status_dir / "latest_overview.md"


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat()


def _write_status(status_dir: Path, job_name: str, payload: dict) -> None:
    status_dir.mkdir(parents=True, exist_ok=True)
    _status_path(status_dir, job_name).write_text(_json_dumps(payload), encoding="utf-8")
    write_latest_overview(status_dir)


def write_latest_overview(status_dir: Path) -> Path:
    status_dir.mkdir(parents=True, exist_ok=True)
    sections: list[str] = ["# iCloud Photo Sync Latest Status", ""]

    for job_name in ("plan", "todo_plan", "apply", "deleted_pool", "onedrive"):
        path = _status_path(status_dir, job_name)
        if not path.exists():
            continue
        payload = _read_json(path)
        sections.append(f"## {job_name}")
        sections.append(f"- status: {payload.get('status', 'unknown')}")
        sections.append(f"- finished_at: {payload.get('finished_at', '-')}")

        if payload.get("status") == "failed":
            sections.append(f"- message: {payload.get('message', '-')}")

        summary = payload.get("summary")
        if isinstance(summary, dict):
            if job_name == "plan":
                sections.append(
                    "- summary: "
                    f"mirror={summary.get('mirror_count', 0)} "
                    f"delete={summary.get('delete_count', 0)} "
                    f"unresolved={summary.get('unresolved_count', 0)}"
                )
            elif job_name == "todo_plan":
                sections.append(
                    "- summary: "
                    f"copy={summary.get('copy_count', 0)} "
                    f"move={summary.get('move_count', 0)} "
                    f"unresolved={summary.get('unresolved_count', 0)}"
                )
            elif job_name == "apply":
                deleted = summary.get("deleted", {})
                mirrored = summary.get("mirrored", {})
                sections.append(
                    "- summary: "
                    f"deleted_moved={deleted.get('moved', 0)} "
                    f"mirror_copied={mirrored.get('copied', 0)} "
                    f"guard_failed={deleted.get('guard_failed', 0) + mirrored.get('guard_failed', 0)}"
                )
            else:
                sections.append(f"- summary: {json.dumps(summary, ensure_ascii=False)}")

        for key in ("plan_dir", "receipt_path"):
            if payload.get(key):
                sections.append(f"- {key}: {payload[key]}")
        sections.append("")

    overview_path = _overview_path(status_dir)
    overview_path.write_text("\n".join(sections).rstrip() + "\n", encoding="utf-8")
    return overview_path


def run_plan_job(
    *,
    library_path: Path,
    db_path: Path,
    nas_root: Path,
    logs_root: Path,
    state_db: Path,
    stage_dir: Path,
    swift_source: Path,
    status_dir: Path,
    plan_id: str | None = None,
    plan_runner: Callable[..., Path] = run_plan,
) -> Path:
    started_at = _now_iso()
    try:
        plan_dir = plan_runner(
            library_path=library_path,
            db_path=db_path,
            nas_root=nas_root,
            logs_root=logs_root,
            state_db=state_db,
            stage_dir=stage_dir,
            swift_source=swift_source,
            plan_id=plan_id,
        )
        summary = _read_json(Path(plan_dir) / "plan_summary.json")
        _write_status(
            status_dir,
            "plan",
            {
                "job_name": "plan",
                "status": "success",
                "exit_code": 0,
                "started_at": started_at,
                "finished_at": _now_iso(),
                "plan_dir": str(plan_dir),
                "summary": summary,
            },
        )
        return plan_dir
    except Exception as exc:  # noqa: BLE001
        _write_status(
            status_dir,
            "plan",
            {
                "job_name": "plan",
                "status": "failed",
                "exit_code": 1,
                "started_at": started_at,
                "finished_at": _now_iso(),
                "message": str(exc),
            },
        )
        raise


def run_apply_job(
    *,
    plan_dir: Path,
    nas_root: Path,
    deleted_root: Path,
    state_db: Path,
    swift_source: Path,
    status_dir: Path,
    apply_runner: Callable[..., Path] = run_apply,
) -> Path:
    started_at = _now_iso()
    try:
        receipt_path = apply_runner(
            plan_dir=plan_dir,
            nas_root=nas_root,
            deleted_root=deleted_root,
            state_db=state_db,
            swift_source=swift_source,
        )
        receipt = _read_json(Path(receipt_path))
        _write_status(
            status_dir,
            "apply",
            {
                "job_name": "apply",
                "status": "success",
                "exit_code": 0,
                "started_at": started_at,
                "finished_at": _now_iso(),
                "plan_dir": str(plan_dir),
                "receipt_path": str(receipt_path),
                "summary": receipt,
            },
        )
        return receipt_path
    except Exception as exc:  # noqa: BLE001
        _write_status(
            status_dir,
            "apply",
            {
                "job_name": "apply",
                "status": "failed",
                "exit_code": 1,
                "started_at": started_at,
                "finished_at": _now_iso(),
                "plan_dir": str(plan_dir),
                "message": str(exc),
            },
        )
        raise


def run_todo_plan_job(
    *,
    source_root: Path,
    target_root: Path,
    review_root: Path,
    logs_root: Path,
    status_dir: Path,
    plan_id: str | None = None,
    plan_runner: Callable[..., Path] = plan_folder_sync,
) -> Path:
    started_at = _now_iso()
    try:
        plan_dir = plan_runner(
            source_root=source_root,
            target_root=target_root,
            review_root=review_root,
            logs_root=logs_root,
            plan_id=plan_id,
        )
        summary = _read_json(Path(plan_dir) / "plan_summary.json")
        _write_status(
            status_dir,
            "todo_plan",
            {
                "job_name": "todo_plan",
                "status": "success",
                "exit_code": 0,
                "started_at": started_at,
                "finished_at": _now_iso(),
                "plan_dir": str(plan_dir),
                "summary": summary,
            },
        )
        return plan_dir
    except Exception as exc:  # noqa: BLE001
        _write_status(
            status_dir,
            "todo_plan",
            {
                "job_name": "todo_plan",
                "status": "failed",
                "exit_code": 1,
                "started_at": started_at,
                "finished_at": _now_iso(),
                "message": str(exc),
            },
        )
        raise


def run_deleted_pool_job(
    *,
    deleted_root: Path,
    logs_root: Path,
    status_dir: Path,
    retention_days: int,
    dry_run: bool = False,
    job_id: str | None = None,
    prune_runner: Callable[..., Path] = prune_deleted_pool,
) -> Path:
    started_at = _now_iso()
    try:
        receipt_path = prune_runner(
            deleted_root=deleted_root,
            logs_root=logs_root,
            retention_days=retention_days,
            job_id=job_id,
            dry_run=dry_run,
        )
        receipt = _read_json(receipt_path)
        exit_code = 0 if receipt.get("status") == "success" else 1
        _write_status(
            status_dir,
            "deleted_pool",
            {
                "job_name": "deleted_pool",
                "status": receipt.get("status", "success"),
                "exit_code": exit_code,
                "started_at": started_at,
                "finished_at": _now_iso(),
                "receipt_path": str(receipt_path),
                "summary": receipt,
            },
        )
        return receipt_path
    except Exception as exc:  # noqa: BLE001
        _write_status(
            status_dir,
            "deleted_pool",
            {
                "job_name": "deleted_pool",
                "status": "failed",
                "exit_code": 1,
                "started_at": started_at,
                "finished_at": _now_iso(),
                "message": str(exc),
            },
        )
        raise


def run_onedrive_backup_job(
    *,
    nas_root: Path,
    deleted_root: Path,
    logs_root: Path,
    onedrive_root: Path,
    status_dir: Path,
    dry_run: bool = False,
    job_id: str | None = None,
    backup_runner: Callable[..., Path] = run_onedrive_backup,
) -> Path:
    started_at = _now_iso()
    try:
        receipt_path = backup_runner(
            nas_root=nas_root,
            deleted_root=deleted_root,
            logs_root=logs_root,
            onedrive_root=onedrive_root,
            job_id=job_id,
            dry_run=dry_run,
        )
        receipt = _read_json(receipt_path)
        exit_code = 0 if receipt.get("status") == "success" else 1
        _write_status(
            status_dir,
            "onedrive",
            {
                "job_name": "onedrive",
                "status": receipt.get("status", "success"),
                "exit_code": exit_code,
                "started_at": started_at,
                "finished_at": _now_iso(),
                "receipt_path": str(receipt_path),
                "summary": receipt,
            },
        )
        return receipt_path
    except Exception as exc:  # noqa: BLE001
        _write_status(
            status_dir,
            "onedrive",
            {
                "job_name": "onedrive",
                "status": "failed",
                "exit_code": 1,
                "started_at": started_at,
                "finished_at": _now_iso(),
                "message": str(exc),
            },
        )
        raise

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Callable

from .deleted_pool import prune_deleted_pool
from .folder_sync import plan_folder_sync
from .mounts import inspect_mount
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


def _write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    temp_path.write_text(text, encoding="utf-8")
    temp_path.replace(path)


def _snapshot(payload: dict) -> dict:
    return {
        key: value
        for key, value in payload.items()
        if key not in {"last_attempt_at", "last_success_at", "last_success", "consecutive_failures"}
    }


def _merge_status(previous: dict, payload: dict) -> dict:
    merged = dict(payload)
    succeeded = payload.get("status") == "success"
    previous_success = previous.get("last_success")
    if previous_success is None and previous.get("status") == "success":
        previous_success = _snapshot(previous)

    merged["last_attempt_at"] = payload.get("finished_at")
    merged["consecutive_failures"] = 0 if succeeded else int(previous.get("consecutive_failures", 0)) + 1
    if succeeded:
        merged["last_success_at"] = payload.get("finished_at")
        merged["last_success"] = _snapshot(payload)
    else:
        merged["last_success_at"] = previous.get("last_success_at")
        merged["last_success"] = previous_success

    if payload.get("job_name") == "plan":
        if succeeded:
            summary = payload.get("summary", {})
            action_count = sum(
                int(summary.get(key, 0))
                for key in ("mirror_count", "delete_count", "unresolved_count")
            )
            merged["pending_plan_dir"] = payload.get("plan_dir") if action_count else None
        else:
            merged["pending_plan_dir"] = previous.get("pending_plan_dir")
    return merged


def _write_status(status_dir: Path, job_name: str, payload: dict) -> None:
    status_dir.mkdir(parents=True, exist_ok=True)
    path = _status_path(status_dir, job_name)
    previous = _read_json(path) if path.exists() else {}
    _write_text_atomic(path, _json_dumps(_merge_status(previous, payload)))
    write_latest_overview(status_dir)


def _render_overview(status_dir: Path, heading: str, job_names: tuple[str, ...]) -> str:
    sections: list[str] = [f"# {heading}", ""]
    for job_name in job_names:
        path = _status_path(status_dir, job_name)
        if not path.exists():
            continue
        payload = _read_json(path)
        sections.append(f"## {job_name}")
        sections.append(f"- status: {payload.get('status', 'unknown')}")
        sections.append(f"- last_attempt_at: {payload.get('last_attempt_at', payload.get('finished_at', '-'))}")
        sections.append(f"- last_success_at: {payload.get('last_success_at') or '-'}")
        sections.append(f"- consecutive_failures: {payload.get('consecutive_failures', 0)}")

        if payload.get("status") == "failed":
            sections.append(f"- message: {payload.get('message', '-')}")
        mount = payload.get("mount")
        if isinstance(mount, dict):
            sections.append(
                f"- mount: {mount.get('mounted_from', '-')} on {mount.get('mount_point', '-')} "
                f"({mount.get('filesystem', '-')})"
            )
        if job_name == "plan":
            sections.append(f"- pending_plan_dir: {payload.get('pending_plan_dir') or '-'}")

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

    return "\n".join(sections).rstrip() + "\n"


def write_latest_overview(status_dir: Path) -> Path:
    status_dir.mkdir(parents=True, exist_ok=True)
    overview_path = _overview_path(status_dir)
    _write_text_atomic(
        overview_path,
        _render_overview(
            status_dir,
            "iCloud Photo Sync Latest Status",
            ("plan", "todo_plan", "apply", "deleted_pool", "onedrive"),
        ),
    )
    _write_text_atomic(
        status_dir / "latest_photo_overview.md",
        _render_overview(
            status_dir,
            "iCloud Photo Center Latest Status",
            ("plan", "apply", "deleted_pool", "onedrive"),
        ),
    )
    _write_text_atomic(
        status_dir / "latest_todo_overview.md",
        _render_overview(status_dir, "ToDo Folder Sync Latest Status", ("todo_plan",)),
    )
    return overview_path


def _inspect_nas_mount(
    *,
    nas_mount_root: Path | None,
    expected_nas_filesystem: str,
    mount_probe: Callable[..., dict],
) -> dict | None:
    if nas_mount_root is None:
        return None
    return mount_probe(
        nas_mount_root,
        expected_filesystems=(expected_nas_filesystem,),
        require_writable=True,
    )


def _clear_pending_plan(status_dir: Path, plan_dir: Path) -> None:
    path = _status_path(status_dir, "plan")
    if not path.exists():
        return
    payload = _read_json(path)
    if payload.get("pending_plan_dir") != str(plan_dir):
        return
    payload["pending_plan_dir"] = None
    _write_text_atomic(path, _json_dumps(payload))
    write_latest_overview(status_dir)


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
    nas_mount_root: Path | None = None,
    expected_nas_filesystem: str = "smbfs",
    plan_runner: Callable[..., Path] = run_plan,
    mount_probe: Callable[..., dict] = inspect_mount,
) -> Path:
    started_at = _now_iso()
    try:
        mount = _inspect_nas_mount(
            nas_mount_root=nas_mount_root,
            expected_nas_filesystem=expected_nas_filesystem,
            mount_probe=mount_probe,
        )
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
                "mount": mount,
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
    nas_mount_root: Path | None = None,
    expected_nas_filesystem: str = "smbfs",
    apply_runner: Callable[..., Path] = run_apply,
    mount_probe: Callable[..., dict] = inspect_mount,
) -> Path:
    started_at = _now_iso()
    try:
        mount = _inspect_nas_mount(
            nas_mount_root=nas_mount_root,
            expected_nas_filesystem=expected_nas_filesystem,
            mount_probe=mount_probe,
        )
        receipt_path = apply_runner(
            plan_dir=plan_dir,
            nas_root=nas_root,
            deleted_root=deleted_root,
            state_db=state_db,
            swift_source=swift_source,
        )
        receipt = _read_json(Path(receipt_path))
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
    status = receipt.get("status", "failed")
    succeeded = status == "success"
    _write_status(
        status_dir,
        "apply",
        {
            "job_name": "apply",
            "status": status,
            "exit_code": 0 if succeeded else 1,
            "started_at": started_at,
            "finished_at": _now_iso(),
            "plan_dir": str(plan_dir),
            "receipt_path": str(receipt_path),
            "summary": receipt,
            "mount": mount,
        },
    )
    if not succeeded:
        raise RuntimeError(f"apply incomplete; inspect receipt: {receipt_path}")
    _clear_pending_plan(status_dir, Path(plan_dir))
    return receipt_path


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
    nas_mount_root: Path | None = None,
    expected_nas_filesystem: str = "smbfs",
    prune_runner: Callable[..., Path] = prune_deleted_pool,
    mount_probe: Callable[..., dict] = inspect_mount,
) -> Path:
    started_at = _now_iso()
    try:
        mount = _inspect_nas_mount(
            nas_mount_root=nas_mount_root,
            expected_nas_filesystem=expected_nas_filesystem,
            mount_probe=mount_probe,
        )
        receipt_path = prune_runner(
            deleted_root=deleted_root,
            logs_root=logs_root,
            retention_days=retention_days,
            job_id=job_id,
            dry_run=dry_run,
        )
        receipt = _read_json(receipt_path)
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
    status = receipt.get("status", "failed")
    succeeded = status == "success"
    _write_status(
        status_dir,
        "deleted_pool",
        {
            "job_name": "deleted_pool",
            "status": status,
            "exit_code": 0 if succeeded else 1,
            "started_at": started_at,
            "finished_at": _now_iso(),
            "receipt_path": str(receipt_path),
            "summary": receipt,
            "mount": mount,
        },
    )
    if not succeeded:
        raise RuntimeError(f"deleted-pool job incomplete; inspect receipt: {receipt_path}")
    return receipt_path


def run_onedrive_backup_job(
    *,
    nas_root: Path,
    deleted_root: Path,
    logs_root: Path,
    onedrive_root: Path,
    status_dir: Path,
    dry_run: bool = False,
    job_id: str | None = None,
    nas_mount_root: Path | None = None,
    expected_nas_filesystem: str = "smbfs",
    backup_runner: Callable[..., Path] = run_onedrive_backup,
    mount_probe: Callable[..., dict] = inspect_mount,
) -> Path:
    started_at = _now_iso()
    try:
        mount = _inspect_nas_mount(
            nas_mount_root=nas_mount_root,
            expected_nas_filesystem=expected_nas_filesystem,
            mount_probe=mount_probe,
        )
        receipt_path = backup_runner(
            nas_root=nas_root,
            deleted_root=deleted_root,
            logs_root=logs_root,
            onedrive_root=onedrive_root,
            job_id=job_id,
            dry_run=dry_run,
        )
        receipt = _read_json(receipt_path)
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
    status = receipt.get("status", "failed")
    succeeded = status == "success"
    _write_status(
        status_dir,
        "onedrive",
        {
            "job_name": "onedrive",
            "status": status,
            "exit_code": 0 if succeeded else 1,
            "started_at": started_at,
            "finished_at": _now_iso(),
            "receipt_path": str(receipt_path),
            "summary": receipt,
            "mount": mount,
        },
    )
    if not succeeded:
        raise RuntimeError(f"OneDrive backup incomplete; inspect receipt: {receipt_path}")
    return receipt_path

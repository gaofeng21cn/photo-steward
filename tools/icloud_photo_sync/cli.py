from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .deleted_pool import prune_deleted_pool
from .folder_sync import apply_folder_plan, plan_folder_sync
from .google_review import apply_google_review_rebucket, plan_google_review_rebucket
from .jobs import (
    run_apply_job,
    run_deleted_pool_job,
    run_onedrive_backup_job,
    run_plan_job,
    run_todo_plan_job,
)
from .mounts import inspect_mount
from .onedrive import run_onedrive_backup
from .runtime import run_apply, run_plan


REPO_ROOT = Path(__file__).resolve().parents[2]
USER_HOME = Path.home()
DEFAULT_LIBRARY_PATH = USER_HOME / "Pictures" / "照片图库.photoslibrary"
DEFAULT_DB_PATH = DEFAULT_LIBRARY_PATH / "database" / "Photos.sqlite"
DEFAULT_NAS_ROOT = Path("/Volumes/home/Photos")
DEFAULT_NAS_MOUNT_ROOT = Path("/Volumes/home")
DEFAULT_LOGS_ROOT = Path("/Volumes/home/Photos_SyncLogs")
DEFAULT_DELETED_ROOT = Path("/Volumes/home/Photos_DeletedFromICloud")
DEFAULT_STATE_DB = REPO_ROOT / "state" / "icloud-photo-sync" / "state.sqlite3"
DEFAULT_STATUS_DIR = REPO_ROOT / "state" / "status"
DEFAULT_STAGE_DIR = REPO_ROOT / "tmp" / "icloud_photo_sync_stage"
DEFAULT_SWIFT_SOURCE = Path(__file__).with_name("photos_bridge.swift")
DEFAULT_ONEDRIVE_ROOT = USER_HOME / "OneDrive" / "Backup" / "icloud-photo-sync"
DEFAULT_FOLDER_LOGS_ROOT = REPO_ROOT / "state" / "folder_sync_logs"
DEFAULT_GOOGLE_REVIEW_LOGS_ROOT = REPO_ROOT / "state" / "google_review_logs"
DEFAULT_TODO_SOURCE_ROOT = USER_HOME / "Documents" / "ToDo"
DEFAULT_TODO_TARGET_ROOT = USER_HOME / "Library" / "CloudStorage" / "OneDrive-个人" / "ToDo"
DEFAULT_TODO_REVIEW_ROOT = (
    USER_HOME / "Library" / "CloudStorage" / "OneDrive-个人" / "ToDo_OneDriveOnlyReview"
)


def _add_nas_mount_contract(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--nas-mount-root", type=Path, default=DEFAULT_NAS_MOUNT_ROOT)
    parser.add_argument("--expected-nas-filesystem", default="smbfs")


def _preflight_nas(args: argparse.Namespace) -> dict:
    return inspect_mount(
        args.nas_mount_root,
        expected_filesystems=(args.expected_nas_filesystem,),
        require_writable=True,
    )


def _load_status_bundle(status_dir: Path, scope: str) -> dict:
    job_names = {
        "photo": ("plan", "apply", "deleted_pool", "onedrive"),
        "todo": ("todo_plan",),
        "all": ("plan", "apply", "deleted_pool", "onedrive", "todo_plan"),
    }[scope]
    jobs = {}
    for job_name in job_names:
        path = status_dir / f"latest_{job_name}.json"
        if path.exists():
            jobs[job_name] = json.loads(path.read_text(encoding="utf-8"))
    return {"scope": scope, "status_dir": str(status_dir), "jobs": jobs}


def _print_receipt_result(receipt_path: Path) -> int:
    print(receipt_path)
    payload = json.loads(Path(receipt_path).read_text(encoding="utf-8"))
    return 0 if payload.get("status") == "success" else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="icloud-photo-sync")
    subparsers = parser.add_subparsers(dest="command", required=True)

    preflight_parser = subparsers.add_parser("preflight")
    _add_nas_mount_contract(preflight_parser)

    status_parser = subparsers.add_parser("status")
    status_parser.add_argument("--status-dir", type=Path, default=DEFAULT_STATUS_DIR)
    status_parser.add_argument("--scope", choices=("photo", "todo", "all"), default="photo")
    status_parser.add_argument("--format", choices=("json", "markdown"), default="json")

    plan_parser = subparsers.add_parser("plan")
    plan_parser.add_argument("--library-path", type=Path, default=DEFAULT_LIBRARY_PATH)
    plan_parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    plan_parser.add_argument("--nas-root", type=Path, default=DEFAULT_NAS_ROOT)
    plan_parser.add_argument("--logs-root", type=Path, default=DEFAULT_LOGS_ROOT)
    plan_parser.add_argument("--state-db", type=Path, default=DEFAULT_STATE_DB)
    plan_parser.add_argument("--stage-dir", type=Path, default=DEFAULT_STAGE_DIR)
    plan_parser.add_argument("--swift-source", type=Path, default=DEFAULT_SWIFT_SOURCE)
    plan_parser.add_argument("--plan-id")
    _add_nas_mount_contract(plan_parser)

    apply_parser = subparsers.add_parser("apply")
    apply_parser.add_argument("--plan-dir", required=True)
    apply_parser.add_argument("--nas-root", type=Path, default=DEFAULT_NAS_ROOT)
    apply_parser.add_argument("--deleted-root", type=Path, default=DEFAULT_DELETED_ROOT)
    apply_parser.add_argument("--state-db", type=Path, default=DEFAULT_STATE_DB)
    apply_parser.add_argument("--swift-source", type=Path, default=DEFAULT_SWIFT_SOURCE)
    _add_nas_mount_contract(apply_parser)

    plan_job_parser = subparsers.add_parser("plan-job")
    plan_job_parser.add_argument("--library-path", type=Path, default=DEFAULT_LIBRARY_PATH)
    plan_job_parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    plan_job_parser.add_argument("--nas-root", type=Path, default=DEFAULT_NAS_ROOT)
    plan_job_parser.add_argument("--logs-root", type=Path, default=DEFAULT_LOGS_ROOT)
    plan_job_parser.add_argument("--state-db", type=Path, default=DEFAULT_STATE_DB)
    plan_job_parser.add_argument("--status-dir", type=Path, default=DEFAULT_STATUS_DIR)
    plan_job_parser.add_argument("--stage-dir", type=Path, default=DEFAULT_STAGE_DIR)
    plan_job_parser.add_argument("--swift-source", type=Path, default=DEFAULT_SWIFT_SOURCE)
    plan_job_parser.add_argument("--plan-id")
    _add_nas_mount_contract(plan_job_parser)

    apply_job_parser = subparsers.add_parser("apply-job")
    apply_job_parser.add_argument("--plan-dir", required=True)
    apply_job_parser.add_argument("--nas-root", type=Path, default=DEFAULT_NAS_ROOT)
    apply_job_parser.add_argument("--deleted-root", type=Path, default=DEFAULT_DELETED_ROOT)
    apply_job_parser.add_argument("--state-db", type=Path, default=DEFAULT_STATE_DB)
    apply_job_parser.add_argument("--status-dir", type=Path, default=DEFAULT_STATUS_DIR)
    apply_job_parser.add_argument("--swift-source", type=Path, default=DEFAULT_SWIFT_SOURCE)
    _add_nas_mount_contract(apply_job_parser)

    prune_parser = subparsers.add_parser("prune-deleted-pool")
    prune_parser.add_argument("--deleted-root", type=Path, default=DEFAULT_DELETED_ROOT)
    prune_parser.add_argument("--logs-root", type=Path, default=DEFAULT_LOGS_ROOT)
    prune_parser.add_argument("--status-dir", type=Path, default=DEFAULT_STATUS_DIR)
    prune_parser.add_argument("--retention-days", type=int, default=30)
    prune_parser.add_argument("--job-id")
    prune_parser.add_argument("--dry-run", action="store_true")
    _add_nas_mount_contract(prune_parser)

    backup_parser = subparsers.add_parser("backup-onedrive")
    backup_parser.add_argument("--nas-root", type=Path, default=DEFAULT_NAS_ROOT)
    backup_parser.add_argument("--deleted-root", type=Path, default=DEFAULT_DELETED_ROOT)
    backup_parser.add_argument("--logs-root", type=Path, default=DEFAULT_LOGS_ROOT)
    backup_parser.add_argument("--status-dir", type=Path, default=DEFAULT_STATUS_DIR)
    backup_parser.add_argument("--onedrive-root", type=Path, default=DEFAULT_ONEDRIVE_ROOT)
    backup_parser.add_argument("--job-id")
    backup_parser.add_argument("--dry-run", action="store_true")
    _add_nas_mount_contract(backup_parser)

    folder_plan_parser = subparsers.add_parser("folder-plan")
    folder_plan_parser.add_argument("--source-root", type=Path, required=True)
    folder_plan_parser.add_argument("--target-root", type=Path, required=True)
    folder_plan_parser.add_argument("--review-root", type=Path, required=True)
    folder_plan_parser.add_argument("--logs-root", type=Path, default=DEFAULT_FOLDER_LOGS_ROOT)
    folder_plan_parser.add_argument("--plan-id")

    folder_apply_parser = subparsers.add_parser("folder-apply")
    folder_apply_parser.add_argument("--plan-dir", required=True)

    google_review_plan_parser = subparsers.add_parser("google-review-plan")
    google_review_plan_parser.add_argument("--review-root", type=Path, required=True)
    google_review_plan_parser.add_argument("--nas-root", type=Path, default=DEFAULT_NAS_ROOT)
    google_review_plan_parser.add_argument("--logs-root", type=Path, default=DEFAULT_GOOGLE_REVIEW_LOGS_ROOT)
    google_review_plan_parser.add_argument("--state-db", type=Path, default=DEFAULT_STATE_DB)
    google_review_plan_parser.add_argument("--plan-id")
    _add_nas_mount_contract(google_review_plan_parser)

    google_review_apply_parser = subparsers.add_parser("google-review-apply")
    google_review_apply_parser.add_argument("--plan-dir", required=True)

    todo_plan_parser = subparsers.add_parser("todo-plan")
    todo_plan_parser.add_argument("--source-root", type=Path, default=DEFAULT_TODO_SOURCE_ROOT)
    todo_plan_parser.add_argument("--target-root", type=Path, default=DEFAULT_TODO_TARGET_ROOT)
    todo_plan_parser.add_argument("--review-root", type=Path, default=DEFAULT_TODO_REVIEW_ROOT)
    todo_plan_parser.add_argument("--logs-root", type=Path, default=DEFAULT_FOLDER_LOGS_ROOT)
    todo_plan_parser.add_argument("--plan-id")

    todo_apply_parser = subparsers.add_parser("todo-apply")
    todo_apply_parser.add_argument("--plan-dir", required=True)

    todo_plan_job_parser = subparsers.add_parser("todo-plan-job")
    todo_plan_job_parser.add_argument("--source-root", type=Path, default=DEFAULT_TODO_SOURCE_ROOT)
    todo_plan_job_parser.add_argument("--target-root", type=Path, default=DEFAULT_TODO_TARGET_ROOT)
    todo_plan_job_parser.add_argument("--review-root", type=Path, default=DEFAULT_TODO_REVIEW_ROOT)
    todo_plan_job_parser.add_argument("--logs-root", type=Path, default=DEFAULT_FOLDER_LOGS_ROOT)
    todo_plan_job_parser.add_argument("--status-dir", type=Path, default=DEFAULT_STATUS_DIR)
    todo_plan_job_parser.add_argument("--plan-id")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "preflight":
        print(json.dumps(_preflight_nas(args), ensure_ascii=False, indent=2))
        return 0

    if args.command == "status":
        if args.format == "json":
            print(json.dumps(_load_status_bundle(args.status_dir, args.scope), ensure_ascii=False, indent=2))
            return 0
        overview_name = "latest_todo_overview.md" if args.scope == "todo" else "latest_photo_overview.md"
        overview_path = args.status_dir / overview_name
        if not overview_path.exists():
            print(f"status overview not found: {overview_path}", file=sys.stderr)
            return 1
        print(overview_path.read_text(encoding="utf-8"), end="")
        return 0

    if args.command == "plan":
        _preflight_nas(args)
        plan_dir = run_plan(
            library_path=args.library_path,
            db_path=args.db_path,
            nas_root=args.nas_root,
            logs_root=args.logs_root,
            state_db=args.state_db,
            stage_dir=args.stage_dir,
            swift_source=args.swift_source,
            plan_id=args.plan_id,
        )
        print(plan_dir)
        return 0

    if args.command == "apply":
        _preflight_nas(args)
        receipt_path = run_apply(
            plan_dir=Path(args.plan_dir),
            nas_root=args.nas_root,
            deleted_root=args.deleted_root,
            state_db=args.state_db,
            swift_source=args.swift_source,
        )
        return _print_receipt_result(receipt_path)

    if args.command == "plan-job":
        try:
            plan_dir = run_plan_job(
                library_path=args.library_path,
                db_path=args.db_path,
                nas_root=args.nas_root,
                logs_root=args.logs_root,
                state_db=args.state_db,
                stage_dir=args.stage_dir,
                swift_source=args.swift_source,
                status_dir=args.status_dir,
                plan_id=args.plan_id,
                nas_mount_root=args.nas_mount_root,
                expected_nas_filesystem=args.expected_nas_filesystem,
            )
        except Exception as exc:  # noqa: BLE001
            print(str(exc), file=sys.stderr)
            return 1
        print(plan_dir)
        return 0

    if args.command == "apply-job":
        try:
            receipt_path = run_apply_job(
                plan_dir=Path(args.plan_dir),
                nas_root=args.nas_root,
                deleted_root=args.deleted_root,
                state_db=args.state_db,
                swift_source=args.swift_source,
                status_dir=args.status_dir,
                nas_mount_root=args.nas_mount_root,
                expected_nas_filesystem=args.expected_nas_filesystem,
            )
        except Exception as exc:  # noqa: BLE001
            print(str(exc), file=sys.stderr)
            return 1
        print(receipt_path)
        return 0

    if args.command == "prune-deleted-pool":
        try:
            receipt_path = run_deleted_pool_job(
                deleted_root=args.deleted_root,
                logs_root=args.logs_root,
                status_dir=args.status_dir,
                retention_days=args.retention_days,
                dry_run=args.dry_run,
                job_id=args.job_id,
                nas_mount_root=args.nas_mount_root,
                expected_nas_filesystem=args.expected_nas_filesystem,
            )
        except Exception as exc:  # noqa: BLE001
            print(str(exc), file=sys.stderr)
            return 1
        print(receipt_path)
        return 0

    if args.command == "backup-onedrive":
        try:
            receipt_path = run_onedrive_backup_job(
                nas_root=args.nas_root,
                deleted_root=args.deleted_root,
                logs_root=args.logs_root,
                onedrive_root=args.onedrive_root,
                status_dir=args.status_dir,
                dry_run=args.dry_run,
                job_id=args.job_id,
                nas_mount_root=args.nas_mount_root,
                expected_nas_filesystem=args.expected_nas_filesystem,
            )
        except Exception as exc:  # noqa: BLE001
            print(str(exc), file=sys.stderr)
            return 1
        print(receipt_path)
        return 0

    if args.command == "folder-plan":
        plan_dir = plan_folder_sync(
            source_root=args.source_root,
            target_root=args.target_root,
            review_root=args.review_root,
            logs_root=args.logs_root,
            plan_id=args.plan_id,
        )
        print(plan_dir)
        return 0

    if args.command == "folder-apply":
        receipt_path = apply_folder_plan(Path(args.plan_dir))
        return _print_receipt_result(receipt_path)

    if args.command == "google-review-plan":
        _preflight_nas(args)
        plan_dir = plan_google_review_rebucket(
            review_root=args.review_root,
            nas_root=args.nas_root,
            logs_root=args.logs_root,
            state_db=args.state_db,
            plan_id=args.plan_id,
        )
        print(plan_dir)
        return 0

    if args.command == "google-review-apply":
        receipt_path = apply_google_review_rebucket(Path(args.plan_dir))
        print(receipt_path)
        return 0

    if args.command == "todo-plan":
        plan_dir = plan_folder_sync(
            source_root=args.source_root,
            target_root=args.target_root,
            review_root=args.review_root,
            logs_root=args.logs_root,
            plan_id=args.plan_id,
        )
        print(plan_dir)
        return 0

    if args.command == "todo-apply":
        receipt_path = apply_folder_plan(Path(args.plan_dir))
        return _print_receipt_result(receipt_path)

    if args.command == "todo-plan-job":
        try:
            plan_dir = run_todo_plan_job(
                source_root=args.source_root,
                target_root=args.target_root,
                review_root=args.review_root,
                logs_root=args.logs_root,
                status_dir=args.status_dir,
                plan_id=args.plan_id,
            )
        except Exception as exc:  # noqa: BLE001
            print(str(exc), file=sys.stderr)
            return 1
        print(plan_dir)
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())

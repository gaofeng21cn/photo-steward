from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import (
    ConfigError,
    activate_config,
    load_config,
    resolve_config_path,
    write_default_config,
    write_setup_config,
)
from .deleted_pool import prune_deleted_pool
from .folder_sync import apply_folder_plan, plan_folder_sync
from .google_review import apply_google_review_rebucket, plan_google_review_rebucket
from .jobs import (
    record_job_failure,
    run_apply_job,
    run_deleted_pool_job,
    run_onedrive_backup_job,
    run_plan_job,
    run_todo_plan_job,
)
from .mounts import MountContractError, inspect_mount
from .onedrive import run_onedrive_backup
from .plan_details import build_plan_details
from .runtime import run_apply, run_plan


DEFAULT_SWIFT_SOURCE = Path(__file__).with_name("photos_bridge.swift")


def _add_nas_mount_contract(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--nas-mount-root", type=Path)
    parser.add_argument("--expected-nas-filesystem")


def _preflight_nas(args: argparse.Namespace) -> dict:
    return inspect_mount(
        args.nas_mount_root,
        expected_filesystems=(args.expected_nas_filesystem,),
        require_writable=True,
    )


def _preflight_or_report(args: argparse.Namespace) -> dict | None:
    try:
        return _preflight_nas(args)
    except MountContractError as exc:
        print(f"NAS mount unavailable: {exc}", file=sys.stderr)
        return None


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


def _apply_config_defaults(args: argparse.Namespace, config) -> None:
    defaults = config.cli_defaults()
    common_fields = (
        "library_path",
        "db_path",
        "nas_mount_root",
        "nas_root",
        "deleted_root",
        "state_db",
        "status_dir",
        "stage_dir",
        "expected_nas_filesystem",
    )
    for field in common_fields:
        if hasattr(args, field) and getattr(args, field) is None:
            setattr(args, field, defaults[field])

    if hasattr(args, "logs_root") and args.logs_root is None:
        if args.command in {"folder-plan", "todo-plan", "todo-plan-job"}:
            args.logs_root = defaults["folder_logs_root"]
        elif args.command == "google-review-plan":
            args.logs_root = defaults["google_review_logs_root"]
        else:
            args.logs_root = defaults["logs_root"]

    if args.command == "backup-onedrive" and args.onedrive_root is None:
        args.onedrive_root = defaults["onedrive_root"]

    if args.command in {"todo-plan", "todo-plan-job"}:
        for field in ("source_root", "target_root", "review_root"):
            if getattr(args, field) is None:
                setattr(args, field, defaults[field])


def _require_arguments(args: argparse.Namespace) -> None:
    required_fields = {
        "preflight": ("nas_mount_root", "expected_nas_filesystem"),
        "status": ("status_dir",),
        "record-failure": ("status_dir",),
        "latest-plan": ("logs_root",),
        "plan-details": ("nas_root",),
        "plan": (
            "library_path",
            "db_path",
            "nas_root",
            "logs_root",
            "state_db",
            "stage_dir",
            "nas_mount_root",
            "expected_nas_filesystem",
        ),
        "apply": ("nas_root", "deleted_root", "state_db", "nas_mount_root", "expected_nas_filesystem"),
        "plan-job": (
            "library_path",
            "db_path",
            "nas_root",
            "logs_root",
            "state_db",
            "status_dir",
            "stage_dir",
            "nas_mount_root",
            "expected_nas_filesystem",
        ),
        "apply-job": (
            "nas_root",
            "deleted_root",
            "state_db",
            "status_dir",
            "nas_mount_root",
            "expected_nas_filesystem",
        ),
        "prune-deleted-pool": (
            "deleted_root",
            "logs_root",
            "status_dir",
            "nas_mount_root",
            "expected_nas_filesystem",
        ),
        "backup-onedrive": (
            "nas_root",
            "deleted_root",
            "logs_root",
            "status_dir",
            "onedrive_root",
            "nas_mount_root",
            "expected_nas_filesystem",
        ),
        "folder-plan": ("source_root", "target_root", "review_root", "logs_root"),
        "google-review-plan": (
            "review_root",
            "nas_root",
            "logs_root",
            "state_db",
            "nas_mount_root",
            "expected_nas_filesystem",
        ),
        "todo-plan": ("source_root", "target_root", "review_root", "logs_root"),
        "todo-plan-job": ("source_root", "target_root", "review_root", "logs_root", "status_dir"),
    }
    missing = [field for field in required_fields.get(args.command, ()) if getattr(args, field, None) is None]
    if missing:
        raise ConfigError(
            "missing configuration for "
            + ", ".join(missing)
            + "; complete config.toml or provide the explicit CLI options"
        )


def _handle_config_command(args: argparse.Namespace) -> int:
    config_path = resolve_config_path(args.config)
    if args.config_action == "path":
        print(config_path)
        return 0
    if args.config_action == "init":
        written_path = write_default_config(config_path, force=args.force)
        activate_config(written_path)
        print(written_path)
        return 0
    if args.config_action == "setup":
        written_path = write_setup_config(
            config_path,
            library_path=args.photos_library,
            nas_photos_path=args.nas_photos,
            force=args.force,
        )
        print(written_path)
        return 0
    if args.config_action == "activate":
        load_config(config_path)
        print(activate_config(config_path))
        return 0
    if args.config_action == "validate":
        print(json.dumps(load_config(config_path).summary(), ensure_ascii=False, indent=2))
        return 0
    return 1


def _latest_plan_dir(logs_root: Path) -> Path:
    candidates: list[tuple[int, Path]] = []
    for summary_path in logs_root.glob("*/**/plan_summary.json"):
        try:
            json.loads(summary_path.read_text(encoding="utf-8"))
            candidates.append((summary_path.stat().st_mtime_ns, summary_path.parent))
        except (OSError, json.JSONDecodeError):
            continue
    if not candidates:
        raise ConfigError(f"no readable plan_summary.json found under {logs_root}")
    return max(candidates, key=lambda candidate: candidate[0])[1]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="photo-steward")
    parser.add_argument(
        "--config",
        type=Path,
        help="private config.toml path; overrides PHOTO_STEWARD_CONFIG and the default user path",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    config_parser = subparsers.add_parser("config", help="create, validate, or locate the private configuration")
    config_subparsers = config_parser.add_subparsers(dest="config_action", required=True)
    config_subparsers.add_parser("path")
    config_init_parser = config_subparsers.add_parser("init")
    config_init_parser.add_argument("--force", action="store_true")
    config_setup_parser = config_subparsers.add_parser(
        "setup",
        help="create a private profile from a Photos library and a mounted NAS photo directory",
    )
    config_setup_parser.add_argument("--photos-library", type=Path, required=True)
    config_setup_parser.add_argument("--nas-photos", type=Path, required=True)
    config_setup_parser.add_argument("--force", action="store_true")
    config_subparsers.add_parser("activate")
    config_subparsers.add_parser("validate")

    preflight_parser = subparsers.add_parser("preflight")
    _add_nas_mount_contract(preflight_parser)

    status_parser = subparsers.add_parser("status")
    status_parser.add_argument("--status-dir", type=Path)
    status_parser.add_argument("--scope", choices=("photo", "todo", "all"), default="photo")
    status_parser.add_argument("--format", choices=("json", "markdown"), default="json")

    record_failure_parser = subparsers.add_parser("record-failure")
    record_failure_parser.add_argument("--status-dir", type=Path)
    record_failure_parser.add_argument("--job-name", required=True)
    record_failure_parser.add_argument("--message", required=True)
    record_failure_parser.add_argument("--exit-code", type=int, required=True)

    latest_plan_parser = subparsers.add_parser("latest-plan")
    latest_plan_parser.add_argument("--logs-root", type=Path)

    plan_details_parser = subparsers.add_parser(
        "plan-details",
        help="read the user-facing review projection for one exact plan",
    )
    plan_details_parser.add_argument("--plan-dir", type=Path, required=True)
    plan_details_parser.add_argument("--nas-root", type=Path)

    plan_parser = subparsers.add_parser("plan")
    plan_parser.add_argument("--library-path", type=Path)
    plan_parser.add_argument("--db-path", type=Path)
    plan_parser.add_argument("--nas-root", type=Path)
    plan_parser.add_argument("--logs-root", type=Path)
    plan_parser.add_argument("--state-db", type=Path)
    plan_parser.add_argument("--stage-dir", type=Path)
    plan_parser.add_argument("--swift-source", type=Path, default=DEFAULT_SWIFT_SOURCE)
    plan_parser.add_argument("--plan-id")
    _add_nas_mount_contract(plan_parser)

    apply_parser = subparsers.add_parser("apply")
    apply_parser.add_argument("--plan-dir", required=True)
    apply_parser.add_argument("--nas-root", type=Path)
    apply_parser.add_argument("--deleted-root", type=Path)
    apply_parser.add_argument("--state-db", type=Path)
    apply_parser.add_argument("--swift-source", type=Path, default=DEFAULT_SWIFT_SOURCE)
    _add_nas_mount_contract(apply_parser)

    plan_job_parser = subparsers.add_parser("plan-job")
    plan_job_parser.add_argument("--library-path", type=Path)
    plan_job_parser.add_argument("--db-path", type=Path)
    plan_job_parser.add_argument("--nas-root", type=Path)
    plan_job_parser.add_argument("--logs-root", type=Path)
    plan_job_parser.add_argument("--state-db", type=Path)
    plan_job_parser.add_argument("--status-dir", type=Path)
    plan_job_parser.add_argument("--stage-dir", type=Path)
    plan_job_parser.add_argument("--swift-source", type=Path, default=DEFAULT_SWIFT_SOURCE)
    plan_job_parser.add_argument("--plan-id")
    _add_nas_mount_contract(plan_job_parser)

    apply_job_parser = subparsers.add_parser("apply-job")
    apply_job_parser.add_argument("--plan-dir", required=True)
    apply_job_parser.add_argument("--nas-root", type=Path)
    apply_job_parser.add_argument("--deleted-root", type=Path)
    apply_job_parser.add_argument("--state-db", type=Path)
    apply_job_parser.add_argument("--status-dir", type=Path)
    apply_job_parser.add_argument("--swift-source", type=Path, default=DEFAULT_SWIFT_SOURCE)
    _add_nas_mount_contract(apply_job_parser)

    prune_parser = subparsers.add_parser("prune-deleted-pool")
    prune_parser.add_argument("--deleted-root", type=Path)
    prune_parser.add_argument("--logs-root", type=Path)
    prune_parser.add_argument("--status-dir", type=Path)
    prune_parser.add_argument("--retention-days", type=int, default=30)
    prune_parser.add_argument("--job-id")
    prune_parser.add_argument("--dry-run", action="store_true")
    _add_nas_mount_contract(prune_parser)

    backup_parser = subparsers.add_parser("backup-onedrive")
    backup_parser.add_argument("--nas-root", type=Path)
    backup_parser.add_argument("--deleted-root", type=Path)
    backup_parser.add_argument("--logs-root", type=Path)
    backup_parser.add_argument("--status-dir", type=Path)
    backup_parser.add_argument("--onedrive-root", type=Path)
    backup_parser.add_argument("--job-id")
    backup_parser.add_argument("--dry-run", action="store_true")
    _add_nas_mount_contract(backup_parser)

    folder_plan_parser = subparsers.add_parser("folder-plan")
    folder_plan_parser.add_argument("--source-root", type=Path, required=True)
    folder_plan_parser.add_argument("--target-root", type=Path, required=True)
    folder_plan_parser.add_argument("--review-root", type=Path, required=True)
    folder_plan_parser.add_argument("--logs-root", type=Path)
    folder_plan_parser.add_argument("--plan-id")

    folder_apply_parser = subparsers.add_parser("folder-apply")
    folder_apply_parser.add_argument("--plan-dir", required=True)

    google_review_plan_parser = subparsers.add_parser("google-review-plan")
    google_review_plan_parser.add_argument("--review-root", type=Path, required=True)
    google_review_plan_parser.add_argument("--nas-root", type=Path)
    google_review_plan_parser.add_argument("--logs-root", type=Path)
    google_review_plan_parser.add_argument("--state-db", type=Path)
    google_review_plan_parser.add_argument("--plan-id")
    _add_nas_mount_contract(google_review_plan_parser)

    google_review_apply_parser = subparsers.add_parser("google-review-apply")
    google_review_apply_parser.add_argument("--plan-dir", required=True)

    todo_plan_parser = subparsers.add_parser("todo-plan")
    todo_plan_parser.add_argument("--source-root", type=Path)
    todo_plan_parser.add_argument("--target-root", type=Path)
    todo_plan_parser.add_argument("--review-root", type=Path)
    todo_plan_parser.add_argument("--logs-root", type=Path)
    todo_plan_parser.add_argument("--plan-id")

    todo_apply_parser = subparsers.add_parser("todo-apply")
    todo_apply_parser.add_argument("--plan-dir", required=True)

    todo_plan_job_parser = subparsers.add_parser("todo-plan-job")
    todo_plan_job_parser.add_argument("--source-root", type=Path)
    todo_plan_job_parser.add_argument("--target-root", type=Path)
    todo_plan_job_parser.add_argument("--review-root", type=Path)
    todo_plan_job_parser.add_argument("--logs-root", type=Path)
    todo_plan_job_parser.add_argument("--status-dir", type=Path)
    todo_plan_job_parser.add_argument("--plan-id")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "config":
        try:
            return _handle_config_command(args)
        except ConfigError as exc:
            print(str(exc), file=sys.stderr)
            return 2

    try:
        config = load_config(resolve_config_path(args.config))
        _apply_config_defaults(args, config)
        _require_arguments(args)
    except ConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if args.command == "preflight":
        payload = _preflight_or_report(args)
        if payload is None:
            return 75
        print(json.dumps(payload, ensure_ascii=False, indent=2))
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

    if args.command == "record-failure":
        record_job_failure(
            status_dir=args.status_dir,
            job_name=args.job_name,
            message=args.message,
            exit_code=args.exit_code,
        )
        return 0

    if args.command == "latest-plan":
        try:
            print(_latest_plan_dir(args.logs_root))
        except ConfigError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        return 0

    if args.command == "plan-details":
        try:
            payload = build_plan_details(args.plan_dir, nas_root=args.nas_root)
        except (OSError, KeyError, json.JSONDecodeError) as exc:
            print(f"cannot read plan details: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    if args.command == "plan":
        if _preflight_or_report(args) is None:
            return 75
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
        if _preflight_or_report(args) is None:
            return 75
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
        if _preflight_or_report(args) is None:
            return 75
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

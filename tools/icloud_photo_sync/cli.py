from __future__ import annotations

import argparse
from pathlib import Path

from .runtime import run_apply, run_plan


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LIBRARY_PATH = Path("/Users/gaofeng/Pictures/照片图库.photoslibrary")
DEFAULT_DB_PATH = DEFAULT_LIBRARY_PATH / "database" / "Photos.sqlite"
DEFAULT_NAS_ROOT = Path("/Volumes/home/Photos")
DEFAULT_LOGS_ROOT = Path("/Volumes/home/Photos_SyncLogs")
DEFAULT_DELETED_ROOT = Path("/Volumes/home/Photos_DeletedFromICloud")
DEFAULT_STATE_DB = REPO_ROOT / "state" / "icloud-photo-sync" / "state.sqlite3"
DEFAULT_STAGE_DIR = REPO_ROOT / "tmp" / "icloud_photo_sync_stage"
DEFAULT_SWIFT_SOURCE = Path(__file__).with_name("photos_bridge.swift")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="icloud-photo-sync")
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan_parser = subparsers.add_parser("plan")
    plan_parser.add_argument("--library-path", type=Path, default=DEFAULT_LIBRARY_PATH)
    plan_parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    plan_parser.add_argument("--nas-root", type=Path, default=DEFAULT_NAS_ROOT)
    plan_parser.add_argument("--logs-root", type=Path, default=DEFAULT_LOGS_ROOT)
    plan_parser.add_argument("--state-db", type=Path, default=DEFAULT_STATE_DB)
    plan_parser.add_argument("--stage-dir", type=Path, default=DEFAULT_STAGE_DIR)
    plan_parser.add_argument("--swift-source", type=Path, default=DEFAULT_SWIFT_SOURCE)
    plan_parser.add_argument("--plan-id")

    apply_parser = subparsers.add_parser("apply")
    apply_parser.add_argument("--plan-dir", required=True)
    apply_parser.add_argument("--nas-root", type=Path, default=DEFAULT_NAS_ROOT)
    apply_parser.add_argument("--deleted-root", type=Path, default=DEFAULT_DELETED_ROOT)
    apply_parser.add_argument("--state-db", type=Path, default=DEFAULT_STATE_DB)
    apply_parser.add_argument("--swift-source", type=Path, default=DEFAULT_SWIFT_SOURCE)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "plan":
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
        receipt_path = run_apply(
            plan_dir=Path(args.plan_dir),
            nas_root=args.nas_root,
            deleted_root=args.deleted_root,
            state_db=args.state_db,
            swift_source=args.swift_source,
        )
        print(receipt_path)
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())

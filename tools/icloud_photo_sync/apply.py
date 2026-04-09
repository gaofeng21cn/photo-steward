from __future__ import annotations

import json
import shutil
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Callable

from .utils import file_state_token, sha256_file


def _load_items(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return list(payload.get("items", []))


def _move_to_pool(source: Path, pool_root: Path, relative_path: str) -> Path:
    destination = pool_root / relative_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(destination))
    return destination


def execute_apply(
    plan_dir: Path,
    nas_root: Path,
    deleted_root: Path,
    exporter: Callable[[dict, Path], Path] | object | None = None,
) -> dict:
    plan_dir = Path(plan_dir)
    nas_root = Path(nas_root)
    deleted_root = Path(deleted_root)

    summary = json.loads((plan_dir / "plan_summary.json").read_text(encoding="utf-8"))
    plan_id = summary["plan_id"]
    delete_items = _load_items(plan_dir / "move_to_nas_deleted_pool.json")
    mirror_items = _load_items(plan_dir / "mirror_to_nas.json")

    deleted_pool_relative_root = f"{date.today().isoformat()}/{plan_id}"
    deleted_pool_root = deleted_root / deleted_pool_relative_root

    receipt = {
        "plan_id": plan_id,
        "deleted_pool_relative_root": deleted_pool_relative_root,
        "deleted": {"moved": 0, "guard_failed": 0, "missing": 0},
        "mirrored": {"copied": 0, "already_present": 0, "guard_failed": 0},
    }

    moved_delete_paths: set[str] = set()
    delete_map = {item["relative_path"]: item for item in delete_items}

    def execute_delete(item: dict) -> bool:
        relative_path = item["relative_path"]
        source = nas_root / relative_path
        if not source.exists():
            receipt["deleted"]["missing"] += 1
            return False
        if file_state_token(source) != item["state_token"]:
            receipt["deleted"]["guard_failed"] += 1
            return False
        _move_to_pool(source, deleted_pool_root, relative_path)
        moved_delete_paths.add(relative_path)
        receipt["deleted"]["moved"] += 1
        return True

    for item in delete_items:
        execute_delete(item)

    with TemporaryDirectory(prefix="icloud-photo-sync-apply-") as temp_root:
        temp_root_path = Path(temp_root)
        batch_exports: dict[str, Path] = {}
        if exporter is not None and hasattr(exporter, "export_batch"):
            remote_actions = [item for item in mirror_items if item["source_kind"] != "local_file"]
            batch_exports = getattr(exporter, "export_batch")(remote_actions, temp_root_path)

        for item in mirror_items:
            target = nas_root / item["target_relative_path"]
            target.parent.mkdir(parents=True, exist_ok=True)

            materialized: Path | None = None
            if item["source_kind"] == "local_file":
                source = Path(item["source_path"])
                if not source.exists() or file_state_token(source) != item["source_state_token"]:
                    receipt["mirrored"]["guard_failed"] += 1
                    continue
                materialized = source
            else:
                if exporter is None:
                    receipt["mirrored"]["guard_failed"] += 1
                    continue
                materialized = batch_exports.get(item["resource_key"])
                if materialized is None:
                    if callable(exporter):
                        materialized = exporter(item, temp_root_path)
                    else:
                        receipt["mirrored"]["guard_failed"] += 1
                        continue

            if sha256_file(materialized) != item["sha256"]:
                receipt["mirrored"]["guard_failed"] += 1
                continue

            if target.exists():
                if sha256_file(target) == item["sha256"]:
                    receipt["mirrored"]["already_present"] += 1
                    continue
                conflict = delete_map.get(item["target_relative_path"])
                if conflict and item["target_relative_path"] not in moved_delete_paths:
                    if not execute_delete(conflict):
                        receipt["mirrored"]["guard_failed"] += 1
                        continue
                elif not conflict:
                    receipt["mirrored"]["guard_failed"] += 1
                    continue

            shutil.copy2(materialized, target)
            if sha256_file(target) != item["sha256"]:
                receipt["mirrored"]["guard_failed"] += 1
                target.unlink(missing_ok=True)
                continue
            receipt["mirrored"]["copied"] += 1

    receipt_path = plan_dir / "apply_receipt.json"
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return receipt

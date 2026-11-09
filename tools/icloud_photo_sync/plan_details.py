from __future__ import annotations

import json
from pathlib import Path

from .review import plan_revision, read_apply_result, read_plan_snapshot


def build_plan_details(plan_dir: Path, *, nas_root: Path | None = None, deleted_root: Path | None = None) -> dict:
    """Return the review-safe, user-facing projection of one exact plan."""
    plan_dir = Path(plan_dir)
    snapshot = read_plan_snapshot(plan_dir)
    summary = json.loads(snapshot["plan_summary.json"])
    mirror_payload = json.loads(snapshot["mirror_to_nas.json"])
    delete_payload = json.loads(snapshot["move_to_nas_deleted_pool.json"])
    revision = plan_revision(plan_dir, nas_root=nas_root, deleted_root=deleted_root, snapshot=snapshot)

    items: list[dict] = []
    for item in mirror_payload.get("items", []):
        items.append(
            {
                "id": f"mirror:{item['resource_key']}",
                "action": "mirror",
                "action_label": "镜像到 NAS",
                "relative_path": item["target_relative_path"],
                "original_filename": item["original_filename"],
                "bytes": int(item.get("bytes", 0)),
                "sha256": item["sha256"],
                "source_kind": item.get("source_kind"),
                "source_path": item.get("source_path"),
                "asset_local_identifier": item.get("asset_local_identifier"),
                "resource_index": item.get("resource_index"),
            }
        )

    for item in delete_payload.get("items", []):
        relative_path = item["relative_path"]
        source_path = str(Path(nas_root) / relative_path) if nas_root is not None else None
        items.append(
            {
                "id": f"quarantine:{relative_path}",
                "action": "quarantine",
                "action_label": "移入隔离池",
                "relative_path": relative_path,
                "original_filename": Path(relative_path).name,
                "bytes": int(item.get("bytes", 0)),
                "sha256": item["sha256"],
                "source_kind": "nas_only",
                "source_path": source_path,
                "asset_local_identifier": None,
                "resource_index": None,
            }
        )

    return {
        "plan_id": summary["plan_id"],
        "revision": revision,
        "targets": {"photos_root": str(nas_root) if nas_root else None, "quarantine_root": str(deleted_root) if deleted_root else None},
        "apply_result": read_apply_result(plan_dir, expected_revision=revision, plan_id=summary["plan_id"]),
        "summary": summary,
        "items": items,
    }

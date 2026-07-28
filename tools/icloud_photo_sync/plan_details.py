from __future__ import annotations

import json
from pathlib import Path


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def build_plan_details(plan_dir: Path, *, nas_root: Path | None = None) -> dict:
    """Return the review-safe, user-facing projection of one exact plan."""
    plan_dir = Path(plan_dir)
    summary = _read_json(plan_dir / "plan_summary.json")
    mirror_payload = _read_json(plan_dir / "mirror_to_nas.json")
    delete_payload = _read_json(plan_dir / "move_to_nas_deleted_pool.json")

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
        "summary": summary,
        "items": items,
    }

import json
from pathlib import Path

from tools.icloud_photo_sync.models import ICloudResource, NasFile
from tools.icloud_photo_sync.planner import build_sync_plan
from tools.icloud_photo_sync.runtime import persist_plan_bundle


def test_persist_plan_bundle_writes_expected_files(tmp_path: Path) -> None:
    resources = [
        ICloudResource(
            resource_key="asset-1:0:IMG_0001.JPG",
            asset_uuid="asset-1",
            asset_local_identifier="asset-1/L0/001",
            resource_index=0,
            original_filename="IMG_0001.JPG",
            created_at="2024-10-10T10:00:00+08:00",
            sha256="sha-a",
            bytes_count=100,
            source_kind="local_file",
            source_path="/source/IMG_0001.JPG",
            source_state_token="src-1",
        )
    ]
    nas_files = [
        NasFile(
            relative_path="2024/10/EXTRA.JPG",
            absolute_path="/nas/2024/10/EXTRA.JPG",
            sha256="sha-x",
            bytes_count=50,
            state_token="nas-1",
        )
    ]
    plan = build_sync_plan(resources, nas_files, {}, "plan-1")
    plan_dir = tmp_path / "plan-1"

    persist_plan_bundle(
        plan_dir=plan_dir,
        plan=plan,
        icloud_resources=resources,
        nas_files=nas_files,
        unresolved=[{"kind": "sample"}],
    )

    assert (plan_dir / "plan_summary.json").exists()
    assert (plan_dir / "present_in_icloud_manifest.jsonl").exists()
    assert (plan_dir / "present_in_nas_manifest.jsonl").exists()
    assert (plan_dir / "mirror_to_nas.json").exists()
    assert (plan_dir / "move_to_nas_deleted_pool.json").exists()
    assert (plan_dir / "unresolved.json").exists()

    summary = json.loads((plan_dir / "plan_summary.json").read_text(encoding="utf-8"))
    assert summary["plan_id"] == "plan-1"
    assert summary["mirror_count"] == 1
    assert summary["delete_count"] == 1
    assert summary["unresolved_count"] == 1

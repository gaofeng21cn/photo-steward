from tools.icloud_photo_sync.models import ICloudResource, NasFile
from tools.icloud_photo_sync.planner import build_sync_plan


def test_planner_reuses_existing_content_and_marks_extra_nas_for_delete() -> None:
    icloud_resources = [
        ICloudResource(
            resource_key="asset-1:0:IMG_1001.JPG",
            asset_uuid="asset-1",
            asset_local_identifier="asset-1/L0/001",
            resource_index=0,
            original_filename="IMG_1001.JPG",
            created_at="2024-10-10T10:00:00+08:00",
            sha256="sha-a",
            bytes_count=100,
            source_kind="local_file",
            source_path="/source/IMG_1001.JPG",
            source_state_token="src-1",
        ),
        ICloudResource(
            resource_key="asset-2:0:IMG_1002.JPG",
            asset_uuid="asset-2",
            asset_local_identifier="asset-2/L0/001",
            resource_index=0,
            original_filename="IMG_1002.JPG",
            created_at="2024-10-11T10:00:00+08:00",
            sha256="sha-b",
            bytes_count=200,
            source_kind="local_file",
            source_path="/source/IMG_1002.JPG",
            source_state_token="src-2",
        ),
    ]
    nas_files = [
        NasFile(
            relative_path="2024/10/IMG_1001.JPG",
            absolute_path="/nas/2024/10/IMG_1001.JPG",
            sha256="sha-a",
            bytes_count=100,
            state_token="nas-1",
        ),
        NasFile(
            relative_path="2024/10/EXTRA.JPG",
            absolute_path="/nas/2024/10/EXTRA.JPG",
            sha256="sha-x",
            bytes_count=150,
            state_token="nas-2",
        ),
    ]

    plan = build_sync_plan(
        icloud_resources=icloud_resources,
        nas_files=nas_files,
        existing_bindings={"asset-1:0:IMG_1001.JPG": "2024/10/IMG_1001.JPG"},
        plan_id="plan-1",
    )

    assert len(plan.mirror_actions) == 1
    assert plan.mirror_actions[0].target_relative_path == "2024/10/IMG_1002.JPG"
    assert len(plan.delete_actions) == 1
    assert plan.delete_actions[0].relative_path == "2024/10/EXTRA.JPG"
    assert plan.bindings["asset-1:0:IMG_1001.JPG"] == "2024/10/IMG_1001.JPG"
    assert plan.bindings["asset-2:0:IMG_1002.JPG"] == "2024/10/IMG_1002.JPG"


def test_planner_preserves_duplicate_instances_by_allocating_dup_suffixes() -> None:
    icloud_resources = [
        ICloudResource(
            resource_key="asset-1:0:IMG_1231.HEIC",
            asset_uuid="asset-1",
            asset_local_identifier="asset-1/L0/001",
            resource_index=0,
            original_filename="IMG_1231.HEIC",
            created_at="2024-10-10T10:00:00+08:00",
            sha256="sha-a",
            bytes_count=100,
            source_kind="local_file",
            source_path="/source/IMG_1231.HEIC",
            source_state_token="src-1",
        ),
        ICloudResource(
            resource_key="asset-2:0:IMG_1231.HEIC",
            asset_uuid="asset-2",
            asset_local_identifier="asset-2/L0/001",
            resource_index=0,
            original_filename="IMG_1231.HEIC",
            created_at="2024-10-10T11:00:00+08:00",
            sha256="sha-b",
            bytes_count=101,
            source_kind="local_file",
            source_path="/source/IMG_1231__v2.HEIC",
            source_state_token="src-2",
        ),
    ]

    plan = build_sync_plan(
        icloud_resources=icloud_resources,
        nas_files=[],
        existing_bindings={},
        plan_id="plan-2",
    )

    targets = sorted(action.target_relative_path for action in plan.mirror_actions)
    assert targets == ["2024/10/IMG_1231.HEIC", "2024/10/IMG_1231__dup1.HEIC"]


def test_planner_relocates_bound_resource_when_date_parent_changes() -> None:
    icloud_resources = [
        ICloudResource(
            resource_key="asset-1:0:4bff8fb24icbad40f25194df33a91bc4.jpg",
            asset_uuid="asset-1",
            asset_local_identifier="asset-1/L0/001",
            resource_index=0,
            original_filename="4bff8fb24icbad40f25194df33a91bc4.jpg",
            created_at="2025-09-20T08:01:29+08:00",
            sha256="sha-a",
            bytes_count=100,
            source_kind="local_file",
            source_path="/source/4bff8fb24icbad40f25194df33a91bc4.jpg",
            source_state_token="src-1",
        )
    ]
    nas_files = [
        NasFile(
            relative_path="2000/01/4bff8fb24icbad40f25194df33a91bc4.jpg",
            absolute_path="/nas/2000/01/4bff8fb24icbad40f25194df33a91bc4.jpg",
            sha256="sha-a",
            bytes_count=100,
            state_token="nas-1",
        )
    ]

    plan = build_sync_plan(
        icloud_resources=icloud_resources,
        nas_files=nas_files,
        existing_bindings={"asset-1:0:4bff8fb24icbad40f25194df33a91bc4.jpg": "2000/01/4bff8fb24icbad40f25194df33a91bc4.jpg"},
        plan_id="plan-3",
    )

    assert len(plan.mirror_actions) == 1
    assert plan.mirror_actions[0].target_relative_path == "2025/09/4bff8fb24icbad40f25194df33a91bc4.jpg"
    assert len(plan.delete_actions) == 1
    assert plan.delete_actions[0].relative_path == "2000/01/4bff8fb24icbad40f25194df33a91bc4.jpg"
    assert plan.bindings["asset-1:0:4bff8fb24icbad40f25194df33a91bc4.jpg"] == "2025/09/4bff8fb24icbad40f25194df33a91bc4.jpg"

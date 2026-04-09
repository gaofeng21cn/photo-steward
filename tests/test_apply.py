import json
from pathlib import Path

from tools.icloud_photo_sync.apply import execute_apply


def _state_token(path: Path) -> str:
    st = path.stat()
    return f"{st.st_size}:{st.st_mtime_ns}:{st.st_ctime_ns}"


def test_execute_apply_moves_delete_candidates_and_copies_new_files(tmp_path: Path) -> None:
    nas_root = tmp_path / "Photos"
    deleted_root = tmp_path / "Photos_DeletedFromICloud"
    plan_dir = tmp_path / "plan"
    source_dir = tmp_path / "source"

    (nas_root / "2024" / "10").mkdir(parents=True)
    deleted_root.mkdir()
    plan_dir.mkdir()
    source_dir.mkdir()

    obsolete = nas_root / "2024" / "10" / "EXTRA.JPG"
    obsolete.write_bytes(b"obsolete")
    source = source_dir / "IMG_1002.JPG"
    source.write_bytes(b"new-photo")

    delete_manifest = {
        "items": [
            {
                "relative_path": "2024/10/EXTRA.JPG",
                "sha256": "b80cd861051aa5903ae63197c8a1e586800bfb3c45b8e3ab44e5892aa93f5975",
                "bytes": 8,
                "state_token": _state_token(obsolete),
            }
        ]
    }
    mirror_manifest = {
        "items": [
            {
                "resource_key": "asset-2:0:IMG_1002.JPG",
                "asset_local_identifier": "asset-2/L0/001",
                "resource_index": 0,
                "original_filename": "IMG_1002.JPG",
                "target_relative_path": "2024/10/IMG_1002.JPG",
                "sha256": "e6adb9d8170e72455af0bd0213571a746d7ac6b2897b1cc1389013c887db2063",
                "bytes": 9,
                "source_kind": "local_file",
                "source_path": str(source),
                "source_state_token": _state_token(source),
            }
        ]
    }

    summary = {"plan_id": "plan-1"}

    (plan_dir / "move_to_nas_deleted_pool.json").write_text(json.dumps(delete_manifest), encoding="utf-8")
    (plan_dir / "mirror_to_nas.json").write_text(json.dumps(mirror_manifest), encoding="utf-8")
    (plan_dir / "plan_summary.json").write_text(json.dumps(summary), encoding="utf-8")

    receipt = execute_apply(
        plan_dir=plan_dir,
        nas_root=nas_root,
        deleted_root=deleted_root,
    )

    assert receipt["deleted"]["moved"] == 1
    assert receipt["mirrored"]["copied"] == 1
    assert (deleted_root / receipt["deleted_pool_relative_root"] / "2024" / "10" / "EXTRA.JPG").exists()
    assert (nas_root / "2024" / "10" / "IMG_1002.JPG").read_bytes() == b"new-photo"


def test_execute_apply_skips_delete_when_guard_fails(tmp_path: Path) -> None:
    nas_root = tmp_path / "Photos"
    deleted_root = tmp_path / "Photos_DeletedFromICloud"
    plan_dir = tmp_path / "plan"

    (nas_root / "2024" / "10").mkdir(parents=True)
    deleted_root.mkdir()
    plan_dir.mkdir()

    obsolete = nas_root / "2024" / "10" / "EXTRA.JPG"
    obsolete.write_bytes(b"changed")

    delete_manifest = {
        "items": [
            {
                "relative_path": "2024/10/EXTRA.JPG",
                "sha256": "wrong-hash",
                "bytes": 7,
                "state_token": "stale-token",
            }
        ]
    }
    (plan_dir / "move_to_nas_deleted_pool.json").write_text(json.dumps(delete_manifest), encoding="utf-8")
    (plan_dir / "mirror_to_nas.json").write_text(json.dumps({"items": []}), encoding="utf-8")
    (plan_dir / "plan_summary.json").write_text(json.dumps({"plan_id": "plan-2"}), encoding="utf-8")

    receipt = execute_apply(
        plan_dir=plan_dir,
        nas_root=nas_root,
        deleted_root=deleted_root,
    )

    assert receipt["deleted"]["guard_failed"] == 1
    assert obsolete.exists()

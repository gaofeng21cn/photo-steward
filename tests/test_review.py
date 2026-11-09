import hashlib
import json
from pathlib import Path

from tools.icloud_photo_sync.apply import execute_apply
from tools.icloud_photo_sync.plan_details import build_plan_details
from tools.icloud_photo_sync.review import apply_reviewed_plan, plan_view, read_apply_result, plan_revision as build_revision
from tools.icloud_photo_sync.utils import file_state_token


def photo_plan(tmp_path):
    plan_dir, nas, deleted = (tmp_path / name for name in ("plan", "nas", "quarantine"))
    for path in (plan_dir, nas, deleted):
        path.mkdir()
    source = tmp_path / "source.jpg"
    source.write_bytes(b"synthetic image")
    (plan_dir / "plan_summary.json").write_text(json.dumps({"plan_id": "review-plan", "mirror_count": 1, "delete_count": 0, "unresolved_count": 0}))
    (plan_dir / "mirror_to_nas.json").write_text(json.dumps({"items": [{
        "resource_key": "sample:0", "original_filename": "source.jpg", "target_relative_path": "photo.jpg",
        "sha256": hashlib.sha256(source.read_bytes()).hexdigest(), "source_kind": "local_file",
        "source_path": str(source), "source_state_token": file_state_token(source), "bytes": source.stat().st_size,
    }]}))
    (plan_dir / "move_to_nas_deleted_pool.json").write_text('{"items": []}')
    return plan_dir, nas, deleted, source


def test_review_apply_reopen_and_retry_keep_same_owner_receipt(tmp_path):
    plan_dir, nas, deleted, source = photo_plan(tmp_path)
    detail = build_plan_details(plan_dir, nas_root=nas, deleted_root=deleted)
    view = plan_view(plan_dir, detail)
    action = view["data"]["items"][0]["actions"][0]["input"]
    calls = []
    def run(snapshot):
        calls.append(True)
        execute_apply(plan_dir, nas, deleted, plan_snapshot=snapshot,
            plan_revision_value=build_revision(plan_dir, nas_root=nas, deleted_root=deleted, snapshot=snapshot))
        return plan_dir / "apply_receipt.json"
    def apply():
        return apply_reviewed_plan(plan_dir=plan_dir, plan_revision_value=action["plan_revision"],
            request_id=action["request_id"], nas_root=nas, deleted_root=deleted, apply_runner=run)
    result = apply()
    assert result["status"] == "success"
    descriptor = json.loads((Path(__file__).parents[1] / "opl-package.json").read_text())
    assert result["readback"]["ref"] in {view["data_ref"] for view in descriptor["app_contributions"]["views"]}
    assert result["readback"]["input"]["plan_dir"] == str(plan_dir)
    assert (nas / "photo.jpg").read_bytes() == source.read_bytes()
    again = apply()
    assert again["replayed"] is True and again["receipt"] == result["receipt"]
    assert len(calls) == 1
    reopened = plan_view(plan_dir, build_plan_details(plan_dir, nas_root=nas, deleted_root=deleted))
    item = reopened["data"]["items"][0]
    assert item["id"] == detail["plan_id"] and item["revision"] == detail["revision"]
    assert item["status"] == "success" and item["actions"] == []
    assert item["plan"]["apply_result"]["operation"]["request_id"] == action["request_id"]


def test_review_rejects_changed_plan_or_target_before_mutation(tmp_path):
    plan_dir, nas, deleted, _ = photo_plan(tmp_path)
    revision = build_plan_details(plan_dir, nas_root=nas, deleted_root=deleted)["revision"]
    def never(snapshot):
        raise AssertionError("a stale plan must not execute")
    changed = apply_reviewed_plan(plan_dir=plan_dir, plan_revision_value=revision, request_id="target",
        nas_root=tmp_path / "different-nas", deleted_root=deleted, apply_runner=never)
    assert changed["error"] == "plan_revision_conflict"
    (plan_dir / "mirror_to_nas.json").write_text('{"items":[]}')
    stale = apply_reviewed_plan(plan_dir=plan_dir, plan_revision_value=revision, request_id="stale",
        nas_root=nas, deleted_root=deleted, apply_runner=never)
    assert stale["error"] == "plan_revision_conflict"
    assert not (plan_dir / "review_apply_operation.json").exists()


def test_unknown_outcome_reopen_does_not_repeat_mutation(tmp_path):
    plan_dir, nas, deleted, _ = photo_plan(tmp_path)
    revision = build_plan_details(plan_dir, nas_root=nas, deleted_root=deleted)["revision"]
    calls = []
    def interrupted(snapshot):
        calls.append(True)
        (nas / "partial-side-effect").write_text("synthetic")
        raise ConnectionError("lost response")
    args = dict(plan_dir=plan_dir, plan_revision_value=revision, request_id="unknown", nas_root=nas,
                deleted_root=deleted, apply_runner=interrupted)
    assert apply_reviewed_plan(**args)["status"] == "outcome_unknown"
    assert apply_reviewed_plan(**args)["status"] == "outcome_unknown"
    assert len(calls) == 1
    assert read_apply_result(plan_dir)["outcome"] == "outcome_unknown"
    assert plan_view(plan_dir, build_plan_details(plan_dir, nas_root=nas, deleted_root=deleted))["data"]["items"][0]["actions"] == []


def test_changed_source_yields_partial_receipt_without_overwrite(tmp_path):
    plan_dir, nas, deleted, source = photo_plan(tmp_path)
    revision = build_plan_details(plan_dir, nas_root=nas, deleted_root=deleted)["revision"]
    source.write_bytes(b"changed after review")
    def run(snapshot):
        execute_apply(plan_dir, nas, deleted, plan_snapshot=snapshot,
            plan_revision_value=build_revision(plan_dir, nas_root=nas, deleted_root=deleted, snapshot=snapshot))
        return plan_dir / "apply_receipt.json"
    result = apply_reviewed_plan(plan_dir=plan_dir, plan_revision_value=revision, request_id="changed-source",
        nas_root=nas, deleted_root=deleted, apply_runner=run)
    assert result["status"] == "partial" and result["receipt"]["mirrored"]["guard_failed"] == 1
    assert not (nas / "photo.jpg").exists()


def test_revoked_mount_rejects_before_operation_claim(tmp_path):
    plan_dir, nas, deleted, _ = photo_plan(tmp_path)
    revision = build_plan_details(plan_dir, nas_root=nas, deleted_root=deleted)["revision"]
    def denied():
        raise PermissionError("permission revoked")
    def never(snapshot):
        raise AssertionError("revoked mount must not mutate")
    result = apply_reviewed_plan(plan_dir=plan_dir, plan_revision_value=revision, request_id="revoked",
        nas_root=nas, deleted_root=deleted, apply_runner=never, preflight=denied)
    assert result["status"] == "rejected" and result["error"] == "preflight_failed"
    assert read_apply_result(plan_dir)["outcome"] == "not_started"


def test_old_receipt_cannot_confirm_a_new_target_revision(tmp_path):
    plan_dir, nas, deleted, _ = photo_plan(tmp_path)
    first = build_plan_details(plan_dir, nas_root=nas, deleted_root=deleted)
    def run(snapshot):
        execute_apply(plan_dir, nas, deleted, plan_snapshot=snapshot,
            plan_revision_value=build_revision(plan_dir, nas_root=nas, deleted_root=deleted, snapshot=snapshot))
        return plan_dir / "apply_receipt.json"
    assert apply_reviewed_plan(plan_dir=plan_dir, plan_revision_value=first["revision"], request_id="first",
        nas_root=nas, deleted_root=deleted, apply_runner=run)["status"] == "success"
    new_target = tmp_path / "new-target"
    new_target.mkdir()
    reviewed = build_plan_details(plan_dir, nas_root=new_target, deleted_root=deleted)
    assert reviewed["revision"] != first["revision"]
    assert reviewed["apply_result"]["outcome"] == "receipt_revision_conflict"
    assert plan_view(plan_dir, reviewed)["data"]["items"][0]["actions"] == []
    def never(snapshot):
        raise AssertionError("old receipt cannot be reused for another target")
    result = apply_reviewed_plan(plan_dir=plan_dir, plan_revision_value=reviewed["revision"], request_id="second",
        nas_root=new_target, deleted_root=deleted, apply_runner=never)
    assert result["status"] == "receipt_revision_conflict"
    assert not (new_target / "photo.jpg").exists()


def test_actual_owner_executes_frozen_review_bytes_when_plan_changes_during_preflight(tmp_path):
    from tools.icloud_photo_sync.runtime import run_apply
    plan_dir, nas, deleted, source = photo_plan(tmp_path)
    first = build_plan_details(plan_dir, nas_root=nas, deleted_root=deleted)
    def change_plan():
        path = plan_dir / "mirror_to_nas.json"
        changed = json.loads(path.read_text())
        changed["items"][0]["target_relative_path"] = "unreviewed.jpg"
        path.write_text(json.dumps(changed))
    def run(snapshot):
        return run_apply(plan_dir=plan_dir, nas_root=nas, deleted_root=deleted,
            state_db=tmp_path / "state.db", swift_source=tmp_path / "unused.swift",
            plan_snapshot=snapshot, expected_plan_revision=first["revision"])
    result = apply_reviewed_plan(plan_dir=plan_dir, plan_revision_value=first["revision"], request_id="frozen",
        nas_root=nas, deleted_root=deleted, apply_runner=run, preflight=change_plan)
    assert result["status"] == "success"
    descriptor = json.loads((Path(__file__).parents[1] / "opl-package.json").read_text())
    assert result["readback"]["ref"] in {view["data_ref"] for view in descriptor["app_contributions"]["views"]}
    assert result["readback"]["input"]["plan_dir"] == str(plan_dir)
    assert (nas / "photo.jpg").read_bytes() == source.read_bytes()
    assert not (nas / "unreviewed.jpg").exists()
    assert result["receipt"]["plan_revision"] == first["revision"]
    reopened = build_plan_details(plan_dir, nas_root=nas, deleted_root=deleted)
    assert reopened["apply_result"]["outcome"] == "receipt_revision_conflict"


def test_legacy_reapply_cannot_replace_the_reviewed_operation_receipt(tmp_path):
    from tools.icloud_photo_sync.runtime import run_apply
    plan_dir, nas, deleted, source = photo_plan(tmp_path)
    first = build_plan_details(plan_dir, nas_root=nas, deleted_root=deleted)
    def run(snapshot):
        return run_apply(plan_dir=plan_dir, nas_root=nas, deleted_root=deleted,
            state_db=tmp_path / "state.db", swift_source=tmp_path / "unused.swift",
            plan_snapshot=snapshot, expected_plan_revision=first["revision"])
    initial = apply_reviewed_plan(plan_dir=plan_dir, plan_revision_value=first["revision"], request_id="original",
        nas_root=nas, deleted_root=deleted, apply_runner=run)
    assert initial["status"] == "success"
    source.write_bytes(b"changed source")
    run_apply(plan_dir=plan_dir, nas_root=nas, deleted_root=deleted,
              state_db=tmp_path / "state.db", swift_source=tmp_path / "unused.swift")
    reopened = build_plan_details(plan_dir, nas_root=nas, deleted_root=deleted)
    result = reopened["apply_result"]
    assert result["outcome"] == "receipt_changed"
    assert result["receipt"]["status"] == "partial"
    assert result["operation"]["receipt"] == initial["receipt"]
    assert result["operation"]["receipt"]["status"] == "success"
    assert plan_view(plan_dir, reopened)["data"]["items"][0]["actions"] == []

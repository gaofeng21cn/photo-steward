"""Owner projections and exact-plan handoff for Agent and shared UI callers."""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
from pathlib import Path
from typing import Callable

PLAN_FILES = ("plan_summary.json", "mirror_to_nas.json", "move_to_nas_deleted_pool.json",
              "proposed_bindings.json", "unresolved.json")
OPERATION_FILE = "review_apply_operation.json"


def plan_revision(plan_dir: Path, *, nas_root: Path | None = None,
                  deleted_root: Path | None = None) -> str:
    # Bind the reviewed plan bytes and both configured mutation targets.
    digest = hashlib.sha256()
    for name in PLAN_FILES:
        path = Path(plan_dir) / name
        data = path.read_bytes() if path.exists() else b""
        digest.update(name.encode() + b"\0" + str(len(data)).encode() + b"\0" + data)
    for target in (nas_root, deleted_root):
        digest.update(b"\0" + (str(Path(target).resolve()) if target else "").encode())
    return "sha256:" + digest.hexdigest()


def read_apply_result(plan_dir: Path) -> dict:
    result = {}
    for key, name in (("operation", OPERATION_FILE), ("receipt", "apply_receipt.json")):
        path = Path(plan_dir) / name
        if path.exists():
            result[key] = json.loads(path.read_text(encoding="utf-8"))
            result[key + "_ref"] = str(path)
    if result.get("operation", {}).get("status") == "started":
        # A missing terminal write is not permission to repeat a mutation.
        result["outcome"] = "outcome_unknown"
    else:
        result["outcome"] = result.get("operation", {}).get("status", result.get("receipt", {}).get("status", "not_started"))
    return result


def status_view(status: dict) -> dict:
    jobs = status.get("jobs", {})
    return {"state": "ready", "result": {**status, "summary": {
        name: {"status": job.get("status"),
               "last_attempt_at": job.get("last_attempt_at", job.get("finished_at")),
               "last_success_at": job.get("last_success_at"),
               "consecutive_failures": job.get("consecutive_failures", 0),
               "pending_plan_dir": job.get("pending_plan_dir"), "summary": job.get("summary")}
        for name, job in jobs.items()
    }}}


def plan_view(plan_dir: Path, plan: dict) -> dict:
    summary = plan["summary"]
    revision = plan["revision"]
    result = plan["apply_result"]
    can_apply = result["outcome"] == "not_started" and not summary.get("unresolved_count", 0)
    request_id = "review:" + hashlib.sha256((str(Path(plan_dir).resolve()) + revision).encode()).hexdigest()
    return {"state": "ready", "data": {"items": [{
        "id": plan["plan_id"], "revision": revision, "title": "照片镜像计划",
        "summary": f"镜像 {summary.get('mirror_count', 0)}，隔离 {summary.get('delete_count', 0)}，未解决 {summary.get('unresolved_count', 0)}",
        "status": "pending" if can_apply else result["outcome"] if result["outcome"] != "not_started" else "blocked",
        "plan_dir": str(plan_dir), "preview": {"target": plan.get("targets"), "before": None,
            "after": "\n".join(f"{item['action_label']}: {item['relative_path']}" for item in plan["items"])},
        "evidence_refs": [str(plan_dir), *[value for key, value in result.items() if key.endswith("_ref")]],
        "actions": [{"action_ref": "photo.steward.v1#plan.apply",
                     "input": {"plan_dir": str(plan_dir), "plan_revision": revision, "request_id": request_id},
                     "label_i18n": {"zh-CN": "执行已审核计划", "en-US": "Apply reviewed plan"}}] if can_apply else [],
        "readback": {"ref": "photo.steward.v1#plan.exact", "input": {"plan_dir": str(plan_dir)}},
        "plan": plan,
    }]}}


def _write_operation(path: Path, operation: dict) -> None:
    temporary = path.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(operation, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def apply_reviewed_plan(*, plan_dir: Path, plan_revision_value: str, request_id: str,
                        nas_root: Path, deleted_root: Path, apply_runner: Callable[[], Path],
                        preflight: Callable[[], object] | None = None) -> dict:
    """Claim one exact plan once; retries return its owner receipt, never reapply."""
    plan_dir = Path(plan_dir)
    base = {"plan_dir": str(plan_dir), "plan_revision": plan_revision_value, "request_id": request_id,
            "readback": {"ref": "photo.steward.v1#plan.exact", "input": {"plan_dir": str(plan_dir)}}}
    if not request_id or len(request_id) > 200:
        return {**base, "status": "rejected", "error": "request_id_invalid"}
    # The claim is stored beside the existing plan/receipt, not in another task store.
    with (plan_dir / ".review-apply.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        current = plan_revision(plan_dir, nas_root=nas_root, deleted_root=deleted_root)
        if current != plan_revision_value:
            return {**base, "status": "rejected", "error": "plan_revision_conflict", "current_revision": current}
        existing = read_apply_result(plan_dir)
        if existing["outcome"] != "not_started":
            return {**base, "status": existing["outcome"], "replayed": True, **existing}
        summary = json.loads((plan_dir / "plan_summary.json").read_text(encoding="utf-8"))
        if summary.get("unresolved_count", 0):
            return {**base, "status": "rejected", "error": "plan_unresolved"}
        if preflight is not None:
            try:
                preflight()
            except Exception as exc:
                return {**base, "status": "rejected", "error": "preflight_failed", "error_type": type(exc).__name__}
        operation_path = plan_dir / OPERATION_FILE
        operation = {**base, "plan_id": summary["plan_id"], "status": "started"}
        _write_operation(operation_path, operation)
        try:
            receipt_path = apply_runner()
            receipt = json.loads(Path(receipt_path).read_text(encoding="utf-8"))
            operation.update(status=receipt.get("status", "outcome_unknown"), receipt_ref=str(receipt_path))
        except Exception as exc:  # the mutation may have completed before its caller failed
            operation.update(status="outcome_unknown", error=type(exc).__name__)
            receipt_path = plan_dir / "apply_receipt.json"
            if receipt_path.exists():
                receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
                if receipt.get("status") == "partial":
                    operation["status"] = "partial"
                operation["receipt_ref"] = str(receipt_path)
        _write_operation(operation_path, operation)
        return {**operation, **read_apply_result(plan_dir)}

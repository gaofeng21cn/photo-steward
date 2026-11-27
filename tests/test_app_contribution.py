from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from test_cli_smoke import _write_config


ROOT = Path(__file__).resolve().parents[1]
MODULE = "photo.steward.v1"


@pytest.fixture
def invoke(tmp_path):
    config = tmp_path / "config.toml"
    _write_config(config, tmp_path)
    manifest = json.loads((ROOT / "opl-package.json").read_text())
    _, script = manifest["provides"]["contribution_handler"]["argv"]

    def run(operation, ref, inputs=None, *, sdk=False):
        envelope = {
            "schema_version": "opl-package-app-contribution-request.v1",
            "operation": operation,
            "package_id": "photo-steward",
        }
        if sdk:
            envelope.update(action_id=ref, payload=inputs, dry_run=False)
        else:
            envelope.update(ref=ref, input=inputs or {})
        completed = subprocess.run(
            [sys.executable, str(ROOT / script)],
            input=json.dumps(envelope),
            capture_output=True,
            text=True,
            check=True,
            cwd=tmp_path,
            env={**os.environ, "PHOTO_STEWARD_CONFIG": str(config)},
        )
        response = json.loads(completed.stdout)
        assert response["schema_version"] == "opl-package-app-contribution-response.v1"
        assert (response["package_id"], response["operation"], response["ref"]) == (
            "photo-steward", operation, ref,
        )
        return response

    return run


def test_reads_status_and_reports_preflight_failure(invoke):
    status = invoke("read", f"{MODULE}#status")
    assert status["ok"] and status["result"]["result"]["scope"] == "photo"
    preflight = invoke("read", f"{MODULE}#preflight")
    assert not preflight["ok"]
    assert "NAS mount unavailable" in preflight["error"]["message"]


def test_pending_and_exact_plan_reads_preserve_review_inputs(invoke, tmp_path):
    assert invoke("read", f"{MODULE}#plan")["result"]["state"] == "empty"

    plan = tmp_path / "plan with spaces"
    plan.mkdir()
    (plan / "plan_summary.json").write_text(
        json.dumps({"plan_id": "sample", "mirror_count": 0, "delete_count": 0, "unresolved_count": 0})
    )
    for filename in ("mirror_to_nas.json", "move_to_nas_deleted_pool.json"):
        (plan / filename).write_text('{"items":[]}')

    status_dir = tmp_path / "state" / "status"
    status_dir.mkdir(parents=True)
    (status_dir / "latest_plan.json").write_text(json.dumps({"pending_plan_dir": str(plan)}))

    pending = invoke("read", f"{MODULE}#plan")
    exact = invoke("read", f"{MODULE}#plan.exact", {"plan_dir": str(plan)})
    reopened = invoke("read", f"{MODULE}#plan", {"plan_dir": str(plan)})
    assert pending["ok"] and exact["ok"] and reopened["ok"]
    assert pending["result"] == exact["result"] == reopened["result"]
    item = exact["result"]["data"]["items"][0]
    action = item["actions"][0]
    assert action["action_ref"] == f"{MODULE}#plan.apply"
    assert action["input"]["plan_dir"] == str(plan)
    assert action["input"]["plan_revision"] == item["revision"]

    stale_inputs = {**action["input"], "plan_revision": "sha256:stale"}
    for sdk in (False, True):
        rejected = invoke("execute", action["action_ref"], stale_inputs, sdk=sdk)
        assert not rejected["ok"]
        assert rejected["error"]["code"] == "plan_revision_conflict"
        assert rejected["result"]["request_id"] == stale_inputs["request_id"]
    assert not (plan / "review_apply_operation.json").exists()


@pytest.mark.parametrize(
    ("operation", "ref", "inputs", "code"),
    [
        ("read", f"{MODULE}#other", {}, "unknown_ref"),
        ("read", f"{MODULE}#plan.exact", {}, "invalid_input"),
        ("read", f"{MODULE}#plan", {"plan_dir": 123}, "invalid_input"),
        ("execute", f"{MODULE}#plan.apply", {"plan_dir": "/missing"}, "invalid_input"),
    ],
)
def test_rejects_unsupported_requests(invoke, operation, ref, inputs, code):
    response = invoke(operation, ref, inputs)
    assert not response["ok"]
    assert response["error"]["code"] == code

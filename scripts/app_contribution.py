#!/usr/bin/env python3
"""Serve OPL Package contribution requests through the Photo Steward CLI."""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.icloud_photo_sync.cli import main as photo_cli

PACKAGE_ID = "photo-steward"
REQUEST_SCHEMA = "opl-package-app-contribution-request.v1"
RESPONSE_SCHEMA = "opl-package-app-contribution-response.v1"
MODULE = "photo.steward.v1"
APPLY_REF = f"{MODULE}#plan.apply"
APPLY_FIELDS = ("plan_dir", "plan_revision", "request_id")
READ_COMMANDS = {
    f"{MODULE}#status": ("status", "--scope", "photo", "--format", "json", "--view"),
    f"{MODULE}#preflight": ("preflight",),
    f"{MODULE}#plan": ("pending-plan", "--view"),
    f"{MODULE}#plan.exact": ("review-view",),
}


def _run_owner(argv: list[str]) -> dict:
    stdout, stderr = io.StringIO(), io.StringIO()
    try:
        with redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = photo_cli(argv)
    except OSError as exc:
        raise ValueError(str(exc)) from exc
    if exit_code != 0:
        raise ValueError(stderr.getvalue().strip() or f"Photo Steward CLI exited with status {exit_code}.")
    result = json.loads(stdout.getvalue())
    if not isinstance(result, dict):
        raise ValueError("Photo Steward CLI did not return a JSON object.")
    return result


def dispatch(request: object) -> dict:
    if not isinstance(request, dict):
        request = {}
    operation = request.get("operation")
    # The dispatcher sends ref/input for the App and action_id/payload for the SDK.
    ref = request.get("ref", request.get("action_id"))
    inputs = request.get("input", request.get("payload", {}))
    response = {
        "schema_version": RESPONSE_SCHEMA,
        "package_id": PACKAGE_ID,
        "operation": operation if isinstance(operation, str) else "",
        "ref": ref if isinstance(ref, str) else "",
    }

    def reject(code: str, message: str) -> dict:
        return {**response, "ok": False, "error": {"code": code, "message": message}}

    if (
        request.get("schema_version") != REQUEST_SCHEMA
        or request.get("package_id") != PACKAGE_ID
        or operation not in ("read", "execute")
        or not isinstance(ref, str)
        or not isinstance(inputs, dict)
        or ("action_id" in request and request["action_id"] != ref)
        or ("input" in request and "payload" in request)
    ):
        return reject("invalid_request", "Invalid Photo Steward contribution request.")

    if operation == "read":
        command = READ_COMMANDS.get(ref)
        if command is None:
            return reject("unknown_ref", f"Unsupported read ref: {ref}")
        argv = list(command)
        if ref in (f"{MODULE}#plan", f"{MODULE}#plan.exact"):
            plan_dir = inputs.get("plan_dir", "")
            if not isinstance(plan_dir, str) or (ref.endswith("#plan.exact") and not plan_dir):
                return reject("invalid_input", "plan_dir must be a string and is required for an exact read.")
            if plan_dir:
                argv.append(f"--plan-dir={plan_dir}")
    else:
        if ref != APPLY_REF:
            return reject("unknown_ref", f"Unsupported action ref: {ref}")
        if any(not isinstance(inputs.get(key), str) or not inputs[key] for key in APPLY_FIELDS):
            return reject("invalid_input", "plan_dir, plan_revision, and request_id are required.")
        if request.get("dry_run", False) is not False:
            return reject("invalid_request", "Use the plan read to preview a Photo Steward apply.")
        argv = ["apply-reviewed-plan", "--contribution"]
        argv.extend(f"--{key.replace('_', '-')}={inputs[key]}" for key in APPLY_FIELDS)

    try:
        result = _run_owner(argv)
    except (KeyError, ValueError) as exc:
        return reject("owner_command_failed", str(exc))
    if operation == "read":
        return {**response, "ok": True, "result": result}
    if (
        result.get("schema_version") != RESPONSE_SCHEMA
        or result.get("operation") != operation
        or result.get("ref") != ref
        or not isinstance(result.get("ok"), bool)
    ):
        return reject("owner_response_invalid", "Photo Steward CLI did not return a valid apply receipt.")
    return {**result, **response}


def main() -> int:
    try:
        request = json.load(sys.stdin)
    except (UnicodeError, json.JSONDecodeError):
        request = None
    print(json.dumps(dispatch(request), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

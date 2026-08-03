#!/bin/zsh
set -u
set -o pipefail

ROOT_DIR="${PHOTO_STEWARD_RUNTIME_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
source "$ROOT_DIR/scripts/lib/automation_common.sh"
cd "$ROOT_DIR"

if ! resolve_python; then
  notify_sync "Python runtime unavailable"
  exit 127
fi
if ! resolve_photo_config; then
  notify_sync "Photo Steward configuration unavailable"
  exit 2
fi

typeset -a jobs
jobs=("plan:$ROOT_DIR/scripts/run_plan.sh")
if [[ "${PHOTO_STEWARD_INCLUDE_TODO:-false}" == true ]]; then
  jobs+=("todo:$ROOT_DIR/scripts/run_todo_plan.sh")
fi

overall_exit=0
receipt_path=""
typeset -a failures
typeset -a results
for job in "${jobs[@]}"; do
  name="${job%%:*}"
  executable="${job#*:}"
  exit_code=0
  if "$executable"; then
    :
  else
    exit_code=$?
    failures+=("${name}=${exit_code}")
    if (( overall_exit == 0 )); then
      overall_exit=$exit_code
    fi
  fi

  business_status="process_failed"
  if (( exit_code == 0 )); then
    scope="photo"
    [[ "$name" == todo ]] && scope="todo"
    status_json="$(photo_cli status --scope "$scope" --format json 2>/dev/null || true)"
    business_status="$(print -r -- "$status_json" | "$PYTHON_BIN" -c '
import json
import sys

name = sys.argv[1]
try:
    payload = json.load(sys.stdin)
except json.JSONDecodeError:
    print("unknown")
    raise SystemExit

job_name = "plan" if name == "plan" else "todo_plan"
job = payload.get("jobs", {}).get(job_name, {})
summary = job.get("summary", {})
if job.get("status") != "success":
    print("failed")
elif int(summary.get("unresolved_count", 0)) > 0 or summary.get("status") == "blocked":
    print("blocked")
elif any(int(summary.get(key, 0)) > 0 for key in ("mirror_count", "delete_count", "copy_count", "move_count")):
    print("review_ready")
else:
    print("current")
' "$name")"
  fi
  results+=("${name}=${exit_code}=${business_status}")
done

config_json="$(photo_cli config validate 2>/dev/null || true)"
receipt_path="$("$PYTHON_BIN" - "$config_json" "$HOME" "$overall_exit" "${results[@]}" <<'PY'
from datetime import datetime
import json
from pathlib import Path
import sys

try:
    config = json.loads(sys.argv[1])
except (TypeError, json.JSONDecodeError):
    config = {}
home = Path(sys.argv[2])
exit_code = int(sys.argv[3])
jobs = {}
for value in sys.argv[4:]:
    name, raw_exit_code, business_status = value.split("=", 2)
    code = int(raw_exit_code)
    jobs[name] = {
        "process_status": "success" if code == 0 else "failed",
        "process_exit_code": code,
        "business_status": business_status,
    }

business_states = {job["business_status"] for job in jobs.values()}
if exit_code != 0:
    status = "failed"
elif "blocked" in business_states or "failed" in business_states or "unknown" in business_states:
    status = "needs_attention"
elif "review_ready" in business_states:
    status = "review_ready"
else:
    status = "success"

now = datetime.now().astimezone()
receipt = {
    "schema_version": 1,
    "job_name": "weekly_orchestrator",
    "status": status,
    "exit_code": exit_code,
    "finished_at": now.isoformat(),
    "jobs": jobs,
}
state_dir = Path(config.get("runtime_state_dir", home / "Library/Application Support/Photo Steward/state"))
receipt_dir = state_dir / "scheduler" / now.strftime("%Y-%m-%d")
receipt_dir.mkdir(parents=True, exist_ok=True)
receipt_path = receipt_dir / f"weekly-{now.strftime('%Y%m%dT%H%M%S')}.json"
receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
latest_path = receipt_dir.parent / "latest_weekly.json"
latest_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(receipt_path)
PY
)" || {
  notify_sync "weekly orchestrator receipt failed"
  (( overall_exit == 0 )) && overall_exit=1
}

if [[ -n "$receipt_path" ]]; then
  print -r -- "$receipt_path"
fi

if (( overall_exit != 0 )); then
  notify_sync "weekly orchestrator incomplete: ${(j:, :)failures}"
fi
exit "$overall_exit"

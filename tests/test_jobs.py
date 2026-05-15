import json
from pathlib import Path

from tools.icloud_photo_sync.jobs import run_plan_job, run_todo_plan_job


def test_run_plan_job_writes_success_status_and_overview(tmp_path: Path) -> None:
    logs_root = tmp_path / "logs"
    state_db = tmp_path / "state.sqlite3"
    status_dir = tmp_path / "status"
    plan_dir = logs_root / "2026-04-10" / "plan-1"
    plan_dir.mkdir(parents=True)
    (plan_dir / "plan_summary.json").write_text(
        json.dumps(
            {
                "plan_id": "plan-1",
                "mirror_count": 2,
                "delete_count": 1,
                "unresolved_count": 0,
                "binding_count": 3,
            }
        ),
        encoding="utf-8",
    )

    def fake_plan_runner(**kwargs):
        return plan_dir

    returned_plan_dir = run_plan_job(
        library_path=tmp_path / "Photos.photoslibrary",
        db_path=tmp_path / "Photos.sqlite",
        nas_root=tmp_path / "Photos",
        logs_root=logs_root,
        state_db=state_db,
        stage_dir=tmp_path / "stage",
        swift_source=tmp_path / "photos_bridge.swift",
        status_dir=status_dir,
        plan_runner=fake_plan_runner,
    )

    latest = json.loads((status_dir / "latest_plan.json").read_text(encoding="utf-8"))
    overview = (status_dir / "latest_overview.md").read_text(encoding="utf-8")

    assert returned_plan_dir == plan_dir
    assert latest["status"] == "success"
    assert latest["plan_dir"] == str(plan_dir)
    assert latest["summary"]["mirror_count"] == 2
    assert "latest_plan.json" not in overview
    assert "mirror=2" in overview


def test_run_plan_job_writes_failure_status_and_reraises(tmp_path: Path) -> None:
    status_dir = tmp_path / "status"

    def fake_plan_runner(**kwargs):
        raise RuntimeError("photos bridge denied")

    try:
        run_plan_job(
            library_path=tmp_path / "Photos.photoslibrary",
            db_path=tmp_path / "Photos.sqlite",
            nas_root=tmp_path / "Photos",
            logs_root=tmp_path / "logs",
            state_db=tmp_path / "state.sqlite3",
            stage_dir=tmp_path / "stage",
            swift_source=tmp_path / "photos_bridge.swift",
            status_dir=status_dir,
            plan_runner=fake_plan_runner,
        )
    except RuntimeError as exc:
        assert str(exc) == "photos bridge denied"
    else:
        raise AssertionError("expected RuntimeError")

    latest = json.loads((status_dir / "latest_plan.json").read_text(encoding="utf-8"))
    assert latest["status"] == "failed"
    assert latest["exit_code"] == 1
    assert "photos bridge denied" in latest["message"]


def test_run_todo_plan_job_writes_success_status_and_overview(tmp_path: Path) -> None:
    logs_root = tmp_path / "folder_sync_logs"
    status_dir = tmp_path / "status"
    plan_dir = logs_root / "2026-04-10" / "todo-plan-1"
    plan_dir.mkdir(parents=True)
    (plan_dir / "plan_summary.json").write_text(
        json.dumps(
            {
                "plan_id": "todo-plan-1",
                "copy_count": 3,
                "move_count": 1,
                "unresolved_count": 0,
                "source_file_count": 10,
                "target_file_count": 8,
            }
        ),
        encoding="utf-8",
    )

    def fake_folder_plan_runner(**kwargs):
        return plan_dir

    returned_plan_dir = run_todo_plan_job(
        source_root=tmp_path / "Documents" / "ToDo",
        target_root=tmp_path / "OneDrive" / "ToDo",
        review_root=tmp_path / "OneDrive" / "ToDo_Review",
        logs_root=logs_root,
        status_dir=status_dir,
        plan_runner=fake_folder_plan_runner,
    )

    latest = json.loads((status_dir / "latest_todo_plan.json").read_text(encoding="utf-8"))
    overview = (status_dir / "latest_overview.md").read_text(encoding="utf-8")

    assert returned_plan_dir == plan_dir
    assert latest["status"] == "success"
    assert latest["plan_dir"] == str(plan_dir)
    assert latest["summary"]["copy_count"] == 3
    assert "## todo_plan" in overview
    assert "copy=3" in overview
    assert "move=1" in overview


def test_run_todo_plan_job_writes_failure_status_and_reraises(tmp_path: Path) -> None:
    status_dir = tmp_path / "status"

    def fake_folder_plan_runner(**kwargs):
        raise RuntimeError("folder sync denied")

    try:
        run_todo_plan_job(
            source_root=tmp_path / "Documents" / "ToDo",
            target_root=tmp_path / "OneDrive" / "ToDo",
            review_root=tmp_path / "OneDrive" / "ToDo_Review",
            logs_root=tmp_path / "folder_sync_logs",
            status_dir=status_dir,
            plan_runner=fake_folder_plan_runner,
        )
    except RuntimeError as exc:
        assert str(exc) == "folder sync denied"
    else:
        raise AssertionError("expected RuntimeError")

    latest = json.loads((status_dir / "latest_todo_plan.json").read_text(encoding="utf-8"))
    assert latest["status"] == "failed"
    assert latest["exit_code"] == 1
    assert "folder sync denied" in latest["message"]

import json
from pathlib import Path

import tools.icloud_photo_sync.cli as cli
from tools.icloud_photo_sync.cli import build_parser
from tools.icloud_photo_sync.mounts import MountContractError


def _write_config(path: Path, root: Path) -> None:
    path.write_text(
        f"""schema_version = 1
[photos]
library_path = "{root / 'Photos Library.photoslibrary'}"
[mirror]
mount_root = "{root / 'nas'}"
photos_root = "{root / 'nas' / 'Photos'}"
quarantine_root = "{root / 'nas' / 'Quarantine'}"
receipts_root = "{root / 'nas' / 'Receipts'}"
expected_filesystem = "smbfs"
[runtime]
state_dir = "{root / 'state'}"
cache_dir = "{root / 'cache'}"
""",
        encoding="utf-8",
    )


def test_cli_parser_supports_all_supported_subcommands() -> None:
    parser = build_parser()

    config_args = parser.parse_args(["config", "path"])
    preflight_args = parser.parse_args(["preflight"])
    status_args = parser.parse_args(["status"])
    plan_details_args = parser.parse_args(["plan-details", "--plan-dir", "/tmp/plan"])
    plan_args = parser.parse_args(["plan"])
    apply_args = parser.parse_args(["apply", "--plan-dir", "/tmp/plan"])
    plan_job_args = parser.parse_args(["plan-job"])
    apply_job_args = parser.parse_args(["apply-job", "--plan-dir", "/tmp/plan"])
    prune_args = parser.parse_args(["prune-deleted-pool"])
    backup_args = parser.parse_args(["backup-onedrive"])
    folder_plan_args = parser.parse_args(
        [
            "folder-plan",
            "--source-root",
            "/tmp/source",
            "--target-root",
            "/tmp/target",
            "--review-root",
            "/tmp/review",
            "--logs-root",
            "/tmp/logs",
        ]
    )
    folder_apply_args = parser.parse_args(["folder-apply", "--plan-dir", "/tmp/plan"])
    google_review_plan_args = parser.parse_args(
        [
            "google-review-plan",
            "--review-root",
            "/tmp/review-root",
        ]
    )
    google_review_apply_args = parser.parse_args(["google-review-apply", "--plan-dir", "/tmp/plan"])
    todo_plan_args = parser.parse_args(["todo-plan"])
    todo_apply_args = parser.parse_args(["todo-apply", "--plan-dir", "/tmp/plan"])
    todo_plan_job_args = parser.parse_args(["todo-plan-job"])
    setup_args = parser.parse_args(
        [
            "config",
            "setup",
            "--photos-library",
            "/tmp/Photos Library.photoslibrary",
            "--nas-photos",
            "/Volumes/nas/Photos",
        ]
    )

    assert config_args.command == "config"
    assert config_args.config_action == "path"
    assert preflight_args.command == "preflight"
    assert status_args.command == "status"
    assert status_args.scope == "photo"
    assert plan_details_args.command == "plan-details"
    assert str(plan_details_args.plan_dir) == "/tmp/plan"
    assert plan_args.command == "plan"
    assert apply_args.command == "apply"
    assert apply_args.plan_dir == "/tmp/plan"
    assert plan_job_args.command == "plan-job"
    assert apply_job_args.command == "apply-job"
    assert apply_job_args.plan_dir == "/tmp/plan"
    assert prune_args.command == "prune-deleted-pool"
    assert backup_args.command == "backup-onedrive"
    assert folder_plan_args.command == "folder-plan"
    assert folder_apply_args.command == "folder-apply"
    assert folder_apply_args.plan_dir == "/tmp/plan"
    assert google_review_plan_args.command == "google-review-plan"
    assert str(google_review_plan_args.review_root) == "/tmp/review-root"
    assert google_review_apply_args.command == "google-review-apply"
    assert google_review_apply_args.plan_dir == "/tmp/plan"
    assert todo_plan_args.command == "todo-plan"
    assert todo_apply_args.command == "todo-apply"
    assert todo_apply_args.plan_dir == "/tmp/plan"
    assert todo_plan_job_args.command == "todo-plan-job"
    assert setup_args.config_action == "setup"
    assert str(setup_args.photos_library) == "/tmp/Photos Library.photoslibrary"


def test_status_command_returns_machine_readable_bundle(tmp_path, capsys) -> None:
    config_path = tmp_path / "config.toml"
    _write_config(config_path, tmp_path)
    status_dir = tmp_path / "status"
    status_dir.mkdir()
    (status_dir / "latest_plan.json").write_text(
        json.dumps({"status": "success", "summary": {"mirror_count": 2}}),
        encoding="utf-8",
    )

    assert cli.main(["--config", str(config_path), "status", "--status-dir", str(status_dir)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["scope"] == "photo"
    assert payload["jobs"]["plan"]["summary"]["mirror_count"] == 2


def test_preflight_command_returns_mount_identity(monkeypatch, tmp_path, capsys) -> None:
    config_path = tmp_path / "config.toml"
    _write_config(config_path, tmp_path)
    monkeypatch.setattr(
        cli,
        "inspect_mount",
        lambda *args, **kwargs: {
            "mount_point": "/Volumes/photo-nas",
            "mounted_from": "//user@nas/home",
            "filesystem": "smbfs",
        },
    )

    assert cli.main(["--config", str(config_path), "preflight"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["mounted_from"] == "//user@nas/home"


def test_missing_config_fails_before_preflight(tmp_path, capsys) -> None:
    missing_path = tmp_path / "missing.toml"

    assert cli.main(["--config", str(missing_path), "preflight"]) == 2
    assert "configuration not found" in capsys.readouterr().err


def test_preflight_reports_mount_failure_without_traceback(monkeypatch, tmp_path, capsys) -> None:
    config_path = tmp_path / "config.toml"
    _write_config(config_path, tmp_path)

    def fail_preflight(*args, **kwargs):
        raise MountContractError(
            "external mount is not present for /Volumes/home; refusing local-root fallback"
        )

    monkeypatch.setattr(cli, "inspect_mount", fail_preflight)

    assert cli.main(["--config", str(config_path), "preflight"]) == 75
    stderr = capsys.readouterr().err
    assert stderr.startswith("NAS mount unavailable: ")
    assert "Traceback" not in stderr


def test_latest_plan_uses_configured_receipts_root(tmp_path, capsys) -> None:
    config_path = tmp_path / "config.toml"
    _write_config(config_path, tmp_path)
    plan_dir = tmp_path / "nas" / "Receipts" / "2026-07-28" / "plan-a"
    plan_dir.mkdir(parents=True)
    (plan_dir / "plan_summary.json").write_text(json.dumps({"plan_id": "plan-a"}), encoding="utf-8")

    assert cli.main(["--config", str(config_path), "latest-plan"]) == 0
    assert capsys.readouterr().out.strip() == str(plan_dir)


def test_plan_details_returns_review_projection(tmp_path, capsys) -> None:
    config_path = tmp_path / "config.toml"
    _write_config(config_path, tmp_path)
    plan_dir = tmp_path / "nas" / "Receipts" / "2026-07-28" / "plan-a"
    plan_dir.mkdir(parents=True)
    (plan_dir / "plan_summary.json").write_text(
        json.dumps(
            {
                "plan_id": "plan-a",
                "mirror_count": 1,
                "delete_count": 1,
                "unresolved_count": 0,
            }
        ),
        encoding="utf-8",
    )
    (plan_dir / "mirror_to_nas.json").write_text(
        json.dumps(
            {
                "items": [
                    {
                        "resource_key": "asset:0:photo.heic",
                        "target_relative_path": "2025/01/photo.heic",
                        "original_filename": "photo.heic",
                        "bytes": 12,
                        "sha256": "a" * 64,
                        "source_kind": "photos_resource_export",
                        "asset_local_identifier": "asset/L0/001",
                        "resource_index": 0,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (plan_dir / "move_to_nas_deleted_pool.json").write_text(
        json.dumps(
            {
                "items": [
                    {
                        "relative_path": "2026/07/IMG_6700.HEIC",
                        "bytes": 34,
                        "sha256": "b" * 64,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    assert cli.main(["--config", str(config_path), "plan-details", "--plan-dir", str(plan_dir)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["plan_id"] == "plan-a"
    assert [item["action"] for item in payload["items"]] == ["mirror", "quarantine"]
    assert payload["items"][1]["source_path"].endswith("/nas/Photos/2026/07/IMG_6700.HEIC")


def test_receipt_result_returns_nonzero_for_partial(tmp_path, capsys) -> None:
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text(json.dumps({"status": "partial"}), encoding="utf-8")

    assert cli._print_receipt_result(receipt_path) == 1
    assert str(receipt_path) in capsys.readouterr().out

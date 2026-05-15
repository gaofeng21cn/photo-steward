from tools.icloud_photo_sync.cli import build_parser


def test_cli_parser_supports_all_supported_subcommands() -> None:
    parser = build_parser()

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

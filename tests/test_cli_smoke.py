from tools.icloud_photo_sync.cli import build_parser


def test_cli_parser_supports_plan_and_apply_subcommands() -> None:
    parser = build_parser()

    plan_args = parser.parse_args(["plan"])
    apply_args = parser.parse_args(["apply", "--plan-dir", "/tmp/plan"])

    assert plan_args.command == "plan"
    assert apply_args.command == "apply"
    assert apply_args.plan_dir == "/tmp/plan"

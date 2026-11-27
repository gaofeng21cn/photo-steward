#!/usr/bin/env python3
"""Validate the root OPL Package v2 manifest and owner entrypoints."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _valid_manifest() -> bool:
    manifest = json.loads((ROOT / "opl-package.json").read_text(encoding="utf-8"))
    identity = manifest.get("identity")
    provides = manifest.get("provides", {})
    declarative = manifest.get("ui", {}).get("declarative", {})
    views = declarative.get("views", [])
    return (
        manifest.get("schema_version") == "opl.package.v2"
        and isinstance(identity, dict)
        and identity.get("id") == "photo-steward"
        and isinstance(identity.get("version"), str)
        and provides.get("contribution_handler") == {
            "kind": "cli",
            "argv": ["python3", "./scripts/app_contribution.py"],
            "transport": "stdin_json_stdout_json",
        }
        and {view.get("id") for view in views}
        == {"photo.steward.plan", "photo.steward.status"}
        and all(
            view.get("slot") != "settings.section"
            or view.get("settings_destination")
            in {"models", "resources", "workspace", "capabilities", "services", "preferences"}
            for view in views
        )
        and any(
            action.get("action_ref") == "photo.steward.v1#plan.apply"
            and action.get("confirm") is True
            for view in views
            for action in view.get("actions", [])
        )
        and (ROOT / "scripts/app_contribution.py").is_file()
        and (ROOT / "scripts/icloud-photo-sync").is_file()
        and (ROOT / "tools/icloud_photo_sync/cli.py").is_file()
        and (ROOT / "skills/photo-steward/SKILL.md").is_file()
        and not (ROOT / "app-contribution-adapter.json").exists()
        and not (ROOT / "plugins/photo-steward").exists()
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="Validate the root manifest (also the default)")
    parser.parse_args()
    valid = _valid_manifest()
    print(json.dumps({"status": "passed" if valid else "stale"}))
    return 0 if valid else 2


if __name__ == "__main__":
    raise SystemExit(main())

import json
from pathlib import Path
import plistlib

import pytest

from tools.icloud_photo_sync import installation as owner


def source_at(path: Path, version="0.4.12"):
    (path / "tools/icloud_photo_sync").mkdir(parents=True)
    (path / "tools/icloud_photo_sync/cli.py").write_text("# domain owner\n")
    (path / "scripts").mkdir()
    (path / "scripts/icloud-photo-sync").write_text("#!/bin/sh\nprintf 'owner-cli\\n'\n")
    (path / "scripts/icloud-photo-sync").chmod(0o755)
    (path / "skills/photo-steward").mkdir(parents=True)
    (path / "skills/photo-steward/SKILL.md").write_text("---\nname: photo-steward\n---\n")
    (path / "opl-package.json").write_text(json.dumps({
        "schema_version": "opl.package.v2",
        "identity": {"id": "photo-steward", "version": version},
    }))
    return path


def bundle_at(path: Path, version="0.4.12", development=False):
    (path / "Contents/MacOS").mkdir(parents=True)
    executable = path / "Contents/MacOS/PhotoCenterMenuBar"
    executable.write_text("#!/bin/sh\nexit 0\n")
    executable.chmod(0o755)
    (path / "Contents/Info.plist").write_bytes(
        plistlib.dumps(
            {
                "CFBundleIdentifier": owner.BUNDLE_ID,
                "CFBundleExecutable": "PhotoCenterMenuBar",
                "CFBundleShortVersionString": version,
                "PhotoStewardDevelopmentBuild": development,
            }
        )
    )
    runtime = source_at(path / owner.RUNTIME_RELATIVE, version)
    (runtime / ".runtime-manifest").write_text(owner._digest(version.encode()))
    return path


def call(home, operation, *args):
    parser = owner.argparse.ArgumentParser()
    owner.configure_parser(parser)
    return owner.execute(parser.parse_args(["--home", str(home), operation, *map(str, args)]))


def selected(snapshot, kind):
    return next(row for row in snapshot["installations"] if row["kind"] == kind)


def test_activate_release_and_development_share_one_pointer_and_preserve_sources(tmp_path):
    home = tmp_path / "home"
    app = bundle_at(home / "Applications" / owner.APP_NAME)
    source = source_at(tmp_path / "checkout")
    snapshot = call(home, "link", "--source", source)
    development = selected(snapshot, "source_link")
    assert development["active"] is True
    assert development["supported_actions"] == ["inspect", "activate", "unlink"]
    release = selected(snapshot, "macos_app")
    assert release["supported_actions"] == ["inspect", "activate"]
    snapshot = call(
        home,
        "activate",
        "--installation-id",
        release["installation_id"],
        "--expected-revision",
        release["revision"],
    )
    release = selected(snapshot, "macos_app")
    development = selected(snapshot, "source_link")
    assert release["active"] is True
    assert development["active"] is False
    assert sum(row["active"] is True for row in snapshot["installations"]) == 1
    assert (home / ".codex/skills/photo-steward").resolve() == (
        owner._runtime_base(home) / "current/skills/photo-steward"
    ).resolve()
    snapshot = call(
        home,
        "activate",
        "--installation-id",
        development["installation_id"],
        "--expected-revision",
        development["revision"],
    )
    development = selected(snapshot, "source_link")
    assert (owner._runtime_base(home) / "current").resolve() == source
    snapshot = call(
        home,
        "unlink",
        "--installation-id",
        development["installation_id"],
        "--expected-revision",
        development["revision"],
    )
    assert source.is_dir()
    assert app.is_dir()
    assert snapshot["active_installation_id"] is None
    assert not any(row["kind"] == "source_link" for row in snapshot["installations"])


def test_changed_pointer_rejects_stale_mutation_before_touching_files(tmp_path):
    home = tmp_path / "home"
    bundle_at(home / "Applications" / owner.APP_NAME)
    first = source_at(tmp_path / "first")
    second = source_at(tmp_path / "second")
    snapshot = call(home, "link", "--source", first)
    release = selected(snapshot, "macos_app")
    call(home, "link", "--source", second)
    with pytest.raises(owner.InstallationError, match="revision_conflict"):
        call(
            home,
            "activate",
            "--installation-id",
            release["installation_id"],
            "--expected-revision",
            release["revision"],
        )
    assert (owner._runtime_base(home) / "current").resolve() == second


def test_prepare_activates_app_bundle_and_refreshes_runtime_after_sparkle_update(tmp_path):
    home = tmp_path / "home"
    app = bundle_at(home / "Applications" / owner.APP_NAME, "0.4.11")
    snapshot = call(home, "prepare", "--app-path", app)
    assert snapshot["active_installation_status"] == "active"
    assert selected(snapshot, "macos_app")["active"] is True
    assert selected(snapshot, "macos_app")["version"] == "0.4.11"

    # Simulate Sparkle replacing the .app bundle in place with a newer version.
    bundle_at(tmp_path / "sparkle-updated" / owner.APP_NAME, "0.4.12")
    import shutil
    shutil.rmtree(app)
    shutil.copytree(tmp_path / "sparkle-updated" / owner.APP_NAME, app)

    updated = call(home, "prepare", "--app-path", app)
    assert updated["active_installation_status"] == "active"
    assert selected(updated, "macos_app")["active"] is True
    assert selected(updated, "macos_app")["version"] == "0.4.12"
    assert call(home, "inspect") == updated


def test_activation_preserves_user_owned_cli_entrypoint(tmp_path):
    home = tmp_path / "home"
    app = bundle_at(home / "Applications" / owner.APP_NAME, "0.4.12")
    command = home / ".local/bin/photo-steward"
    command.parent.mkdir(parents=True)
    command.write_text("#!/bin/sh\n# custom user command\n")
    with pytest.raises(owner.InstallationError, match="cli_entrypoint_conflict"):
        call(home, "prepare", "--app-path", app)
    assert "custom user command" in command.read_text()


def test_inspect_is_offline_and_does_not_ship_hand_rolled_app_updater(tmp_path):
    assert call(tmp_path / "unconfigured", "inspect")["installations"] == []
    source_text = Path(owner.__file__).read_text(encoding="utf-8")
    for forbidden in ("urllib.request", "zipfile", "/usr/bin/ditto", "/usr/bin/codesign", "/usr/sbin/spctl", "/usr/bin/pgrep"):
        assert forbidden not in source_text
    assert not hasattr(owner, "read_release")
    assert not hasattr(owner, "_download_and_install")


def test_legacy_disagreement_requires_explicit_activation(tmp_path):
    home = tmp_path / "home"
    app = bundle_at(home / "Applications" / owner.APP_NAME)
    source = source_at(tmp_path / "source")
    call(home, "link", "--source", source)
    current = owner._runtime_base(home) / "current"
    current.unlink()
    current.symlink_to(app / owner.RUNTIME_RELATIVE)
    cli = home / ".local/bin/photo-steward"
    cli.unlink()
    cli.symlink_to(source / "scripts/icloud-photo-sync")
    snapshot = call(home, "inspect")
    assert snapshot["active_installation_status"] == "conflict"
    assert snapshot["active_installation_id"] is None
    release = selected(snapshot, "macos_app")
    snapshot = call(
        home,
        "activate",
        "--installation-id",
        release["installation_id"],
        "--expected-revision",
        release["revision"],
    )
    assert snapshot["active_installation_status"] == "active"
    assert selected(snapshot, "macos_app")["active"] is True


def test_native_package_and_python_versions_match():
    import tomllib

    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root / "opl-package.json").read_text())
    project = tomllib.loads((root / "pyproject.toml").read_text())
    info = plistlib.loads((root / "app/PhotoCenterMenuBar/Info.plist").read_bytes())
    assert manifest["schema_version"] == "opl.package.v2"
    assert project["project"]["version"] == info["CFBundleShortVersionString"] == manifest["identity"]["version"]
    assert manifest["identity"]["intent"] == "app"

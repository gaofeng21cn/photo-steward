import json
from pathlib import Path
import plistlib

import pytest

from tools.icloud_photo_sync import installation as owner


def source_at(path: Path, version="0.4.8"):
    (path / "tools/icloud_photo_sync").mkdir(parents=True)
    (path / "tools/icloud_photo_sync/cli.py").write_text("# domain owner\n")
    (path / "scripts").mkdir()
    (path / "scripts/icloud-photo-sync").write_text("#!/bin/sh\nprintf 'owner-cli\\n'\n")
    (path / "scripts/icloud-photo-sync").chmod(0o755)
    (path / "skills/photo-steward").mkdir(parents=True)
    (path / "skills/photo-steward/SKILL.md").write_text("---\nname: photo-steward\n---\n")
    (path / "opl-package.json").write_text(json.dumps({"package_id": "photo-steward", "version": version}))
    return path


def bundle_at(path: Path, version="0.4.8", development=False):
    (path / "Contents/MacOS").mkdir(parents=True)
    executable = path / "Contents/MacOS/PhotoCenterMenuBar"
    executable.write_text("#!/bin/sh\nexit 0\n")
    executable.chmod(0o755)
    (path / "Contents/Info.plist").write_bytes(plistlib.dumps({
        "CFBundleIdentifier": owner.BUNDLE_ID, "CFBundleExecutable": "PhotoCenterMenuBar",
        "CFBundleShortVersionString": version, "PhotoStewardDevelopmentBuild": development,
    }))
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
    assert "update" not in development["supported_actions"]
    release = selected(snapshot, "macos_app")
    snapshot = call(home, "activate", "--installation-id", release["installation_id"], "--expected-revision", release["revision"])
    release = selected(snapshot, "macos_app")
    development = selected(snapshot, "source_link")
    assert release["active"] is True
    assert development["active"] is False
    assert sum(row["active"] is True for row in snapshot["installations"]) == 1
    assert (home / ".codex/skills/photo-steward").resolve() == (owner._runtime_base(home) / "current/skills/photo-steward").resolve()
    snapshot = call(home, "activate", "--installation-id", development["installation_id"], "--expected-revision", development["revision"])
    development = selected(snapshot, "source_link")
    assert (owner._runtime_base(home) / "current").resolve() == source
    snapshot = call(home, "unlink", "--installation-id", development["installation_id"], "--expected-revision", development["revision"])
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
        call(home, "uninstall", "--installation-id", release["installation_id"], "--expected-revision", release["revision"])
    assert (home / "Applications" / owner.APP_NAME).exists()
    assert (owner._runtime_base(home) / "current").resolve() == second


def test_uninstall_preserves_private_configuration_and_other_installations(tmp_path):
    home = tmp_path / "home"
    app = bundle_at(home / "Applications" / owner.APP_NAME)
    config = home / "Library/Application Support/Photo Steward/config.toml"
    config.parent.mkdir(parents=True)
    config.write_text("private-sentinel")
    snapshot = call(home, "inspect")
    release = selected(snapshot, "macos_app")
    snapshot = call(home, "activate", "--installation-id", release["installation_id"], "--expected-revision", release["revision"])
    release = selected(snapshot, "macos_app")
    snapshot = call(home, "uninstall", "--installation-id", release["installation_id"], "--expected-revision", release["revision"])
    assert not app.exists()
    assert config.read_text() == "private-sentinel"
    assert snapshot["active_installation_id"] is None
    assert not (home / ".local/bin/photo-steward").exists()


def test_installer_rollback_preserves_user_owned_entrypoint(tmp_path, monkeypatch):
    home = tmp_path / "home"
    original = bundle_at(home / "Applications" / owner.APP_NAME, "0.4.2")
    new = bundle_at(tmp_path / "new" / owner.APP_NAME)
    command = home / ".local/bin/photo-steward"
    command.parent.mkdir(parents=True)
    command.write_text("#!/bin/sh\n# custom user command\n")
    snapshot = call(home, "inspect")
    release = selected(snapshot, "macos_app")
    monkeypatch.setattr(owner, "_verify_bundle", lambda *args: None)
    with pytest.raises(owner.InstallationError, match="cli_entrypoint_conflict"):
        call(home, "install-bundle", "--bundle", new, "--version", "0.4.8", "--expected-revision", release["revision"])
    assert owner._app(original)["version"] == "0.4.2"
    assert "custom user command" in command.read_text()


def test_install_update_activation_and_idempotent_readback(tmp_path, monkeypatch):
    home = tmp_path / "home"
    first = bundle_at(tmp_path / "v1" / owner.APP_NAME, "0.4.2")
    second = bundle_at(tmp_path / "v2" / owner.APP_NAME, "0.4.8")
    monkeypatch.setattr(owner, "_verify_bundle", lambda *args: None)
    snapshot = call(home, "install-bundle", "--bundle", first, "--version", "0.4.2")
    installed = selected(snapshot, "macos_app")
    assert installed["active"] is True
    snapshot = call(home, "install-bundle", "--bundle", second, "--version", "0.4.8", "--expected-revision", installed["revision"])
    installed = selected(snapshot, "macos_app")
    assert installed["version"] == "0.4.8"
    assert installed["active"] is True
    assert call(home, "inspect") == snapshot


def test_inspect_does_not_read_business_configuration_or_network(tmp_path, monkeypatch):
    monkeypatch.setattr(owner, "urlopen", lambda *args, **kwargs: pytest.fail("inspect must be offline"))
    assert call(tmp_path / "unconfigured", "inspect")["installations"] == []


def test_cannot_install_unverified_release_or_update_development(tmp_path, monkeypatch):
    home = tmp_path / "home"
    candidate = bundle_at(tmp_path / "new" / owner.APP_NAME)
    monkeypatch.setattr(owner, "_verify_bundle", lambda *args: (_ for _ in ()).throw(owner.InstallationError("signature_invalid")))
    with pytest.raises(owner.InstallationError, match="signature_invalid"):
        call(home, "install-bundle", "--bundle", candidate, "--version", "0.4.8")
    source = source_at(tmp_path / "source")
    development = selected(call(home, "link", "--source", source), "source_link")
    with pytest.raises(owner.InstallationError, match="development_updates_owned"):
        call(home, "update", "--installation-id", development["installation_id"], "--expected-revision", development["revision"], "--version", "0.4.8")
    assert source.is_dir()


def test_release_install_does_not_steal_development_selection(tmp_path, monkeypatch):
    home = tmp_path / "home"
    source = source_at(tmp_path / "source")
    call(home, "link", "--source", source)
    candidate = bundle_at(tmp_path / "new" / owner.APP_NAME)
    monkeypatch.setattr(owner, "_verify_bundle", lambda *args: None)
    snapshot = call(home, "install-bundle", "--bundle", candidate, "--version", "0.4.8")
    assert selected(snapshot, "source_link")["active"] is True
    assert selected(snapshot, "macos_app")["active"] is False


def test_legacy_disagreement_requires_explicit_activation(tmp_path):
    home = tmp_path / "home"
    app = bundle_at(home / "Applications" / owner.APP_NAME)
    source = source_at(tmp_path / "source")
    snapshot = call(home, "link", "--source", source)
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
    snapshot = call(home, "activate", "--installation-id", release["installation_id"], "--expected-revision", release["revision"])
    assert snapshot["active_installation_status"] == "active"
    assert selected(snapshot, "macos_app")["active"] is True


def test_native_package_and_python_versions_match():
    import tomllib
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root / "opl-package.json").read_text())
    project = tomllib.loads((root / "pyproject.toml").read_text())
    info = plistlib.loads((root / "app/PhotoCenterMenuBar/Info.plist").read_bytes())
    assert project["project"]["version"] == info["CFBundleShortVersionString"] == manifest["version"]
    assert manifest["presentation"]["software_type"] == "application"

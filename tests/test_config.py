from __future__ import annotations

import stat
from pathlib import Path

import pytest

from tools.icloud_photo_sync.config import (
    CONFIG_ENV_VAR,
    ConfigError,
    LEGACY_CONFIG_ENV_VAR,
    active_config_path_file,
    activate_config,
    default_config_path,
    load_config,
    resolve_config_path,
    write_default_config,
    write_setup_config,
)


def _write_config(path: Path, root: Path, *, extra: str = "") -> None:
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
{extra}
""",
        encoding="utf-8",
    )


def test_default_config_path_is_outside_the_repository(tmp_path: Path) -> None:
    path = default_config_path(tmp_path)
    assert path == tmp_path / "Library" / "Application Support" / "Photo Steward" / "config.toml"


def test_load_config_derives_runtime_and_database_paths(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    _write_config(config_path, tmp_path)

    config = load_config(config_path)

    assert config.database_path == tmp_path / "Photos Library.photoslibrary" / "database" / "Photos.sqlite"
    assert config.cli_defaults()["status_dir"] == tmp_path / "state" / "status"
    assert config.cli_defaults()["stage_dir"] == tmp_path / "cache" / "stage"


def test_runtime_overrides_preserve_an_existing_state_layout(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    _write_config(
        config_path,
        tmp_path,
        extra=f'''\nstate_db = "{tmp_path / "legacy" / "state.sqlite3"}"\nstatus_dir = "{tmp_path / "legacy-status"}"\nstage_dir = "{tmp_path / "legacy-stage"}"''',
    )

    config = load_config(config_path)

    assert config.state_db == tmp_path / "legacy" / "state.sqlite3"
    assert config.status_dir == tmp_path / "legacy-status"
    assert config.stage_dir == tmp_path / "legacy-stage"


def test_config_path_precedence(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    environment_path = tmp_path / "environment.toml"
    explicit_path = tmp_path / "explicit.toml"
    monkeypatch.setenv(CONFIG_ENV_VAR, str(environment_path))

    assert resolve_config_path() == environment_path
    assert resolve_config_path(explicit_path) == explicit_path


def test_legacy_config_environment_variable_remains_supported(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    legacy_path = tmp_path / "legacy.toml"
    monkeypatch.delenv(CONFIG_ENV_VAR, raising=False)
    monkeypatch.setenv(LEGACY_CONFIG_ENV_VAR, str(legacy_path))

    assert resolve_config_path() == legacy_path


def test_active_configuration_path_is_used_without_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config_path = tmp_path / "config.toml"
    pointer_path = active_config_path_file(tmp_path)
    pointer_path.parent.mkdir(parents=True)
    pointer_path.write_text(f"{config_path}\n", encoding="utf-8")
    monkeypatch.delenv(CONFIG_ENV_VAR, raising=False)
    monkeypatch.delenv(LEGACY_CONFIG_ENV_VAR, raising=False)
    monkeypatch.setattr("tools.icloud_photo_sync.config.active_config_path_file", lambda: pointer_path)

    assert resolve_config_path() == config_path


def test_activate_config_writes_private_pointer(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    pointer_path = tmp_path / "active-config-path"
    monkeypatch.setattr("tools.icloud_photo_sync.config.active_config_path_file", lambda: pointer_path)

    assert activate_config(config_path) == pointer_path
    assert pointer_path.read_text(encoding="utf-8") == f"{config_path}\n"
    assert stat.S_IMODE(pointer_path.stat().st_mode) == 0o600


def test_default_config_creation_is_private_and_non_destructive(tmp_path: Path) -> None:
    config_path = tmp_path / "nested" / "config.toml"

    write_default_config(config_path)

    assert stat.S_IMODE(config_path.stat().st_mode) == 0o600
    with pytest.raises(ConfigError, match="already exists"):
        write_default_config(config_path)


def test_config_rejects_secrets_and_paths_outside_mount(tmp_path: Path) -> None:
    secret_path = tmp_path / "secret.toml"
    _write_config(secret_path, tmp_path, extra='\n[credentials]\ntoken = "do-not-store"')
    with pytest.raises(ConfigError, match="must not be stored"):
        load_config(secret_path)

    unknown_key_path = tmp_path / "unknown-key.toml"
    _write_config(unknown_key_path, tmp_path, extra='\nnas_password = "do-not-store"')
    with pytest.raises(ConfigError, match="unknown key"):
        load_config(unknown_key_path)

    outside_path = tmp_path / "outside.toml"
    outside_path.write_text(
        f"""schema_version = 1
[photos]
library_path = "{tmp_path / 'Library.photoslibrary'}"
[mirror]
mount_root = "{tmp_path / 'nas'}"
photos_root = "{tmp_path / 'elsewhere' / 'Photos'}"
quarantine_root = "{tmp_path / 'nas' / 'Quarantine'}"
receipts_root = "{tmp_path / 'nas' / 'Receipts'}"
expected_filesystem = "smbfs"
[runtime]
state_dir = "{tmp_path / 'state'}"
cache_dir = "{tmp_path / 'cache'}"
""",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="must be below"):
        load_config(outside_path)


def test_first_run_setup_writes_private_profile_from_two_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    library = tmp_path / "Photos Library.photoslibrary"
    nas_mount = tmp_path / "nas"
    nas_photos = nas_mount / "Photos"
    library.mkdir()
    nas_photos.mkdir(parents=True)
    config_path = tmp_path / "Library" / "Application Support" / "Photo Steward" / "config.toml"
    monkeypatch.setattr(
        "tools.icloud_photo_sync.config.default_config_path",
        lambda home=None: config_path,
    )

    written = write_setup_config(
        config_path,
        library_path=library,
        nas_photos_path=nas_photos,
        mount_probe=lambda *args, **kwargs: {
            "mount_point": str(nas_mount),
            "filesystem": "smbfs",
        },
    )

    assert written == config_path
    assert config_path.stat().st_mode & 0o777 == 0o600
    config = load_config(config_path)
    assert config.library_path == library
    assert config.mount_root == nas_mount
    assert config.photos_root == nas_photos
    assert config.quarantine_root == nas_mount / "PhotoSteward_Quarantine"
    assert config.receipts_root == nas_mount / "PhotoSteward_Receipts"
    assert config.expected_filesystem == "smbfs"
    assert config_path.with_name("active-config-path").read_text(encoding="utf-8") == f"{config_path}\n"

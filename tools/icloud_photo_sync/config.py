from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 compatibility
    import tomli as tomllib

from .mounts import inspect_mount


APP_NAME = "Photo Steward"
CONFIG_ENV_VAR = "PHOTO_STEWARD_CONFIG"
LEGACY_CONFIG_ENV_VAR = "ICLOUD_PHOTO_SYNC_CONFIG"
SCHEMA_VERSION = 1
SENSITIVE_KEYWORDS = {"api_key", "credential", "password", "secret", "token"}
TOP_LEVEL_KEYS = {"schema_version", "photos", "mirror", "runtime", "backup", "extensions"}
TABLE_KEYS = {
    "photos": {"library_path", "database_path"},
    "mirror": {"mount_root", "photos_root", "quarantine_root", "receipts_root", "expected_filesystem"},
    "runtime": {"state_dir", "cache_dir", "state_db", "status_dir", "stage_dir"},
    "backup": {"onedrive_root"},
    "extensions": {"todo"},
    "extensions.todo": {"source_root", "target_root", "review_root"},
}

DEFAULT_CONFIG_TEMPLATE = """# Photo Steward local configuration.
#
# This file is private. Keep real paths, NAS names, user names, and all runtime
# state outside the repository. Do not put passwords, cloud tokens, or photos
# in this file; use macOS Keychain or the relevant backup tool instead.
schema_version = 1

[photos]
library_path = "~/Pictures/Photos Library.photoslibrary"
# database_path is optional. By default Photo Steward uses
# <library_path>/database/Photos.sqlite.

[mirror]
mount_root = "/Volumes/your-nas"
photos_root = "/Volumes/your-nas/Photos"
quarantine_root = "/Volumes/your-nas/PhotoSteward_Quarantine"
receipts_root = "/Volumes/your-nas/PhotoSteward_Receipts"
expected_filesystem = "smbfs"

[runtime]
state_dir = "~/Library/Application Support/Photo Steward/state"
cache_dir = "~/Library/Caches/Photo Steward"
# Optional compatibility overrides for a pre-existing state layout:
# state_db = "~/Library/Application Support/Photo Steward/state/state.sqlite3"
# status_dir = "~/Library/Application Support/Photo Steward/status"
# stage_dir = "~/Library/Caches/Photo Steward/stage"

# Optional off-site backup adapter. Leave this section out when unused.
# [backup]
# onedrive_root = "~/OneDrive/Backup/PhotoSteward"

# Optional advanced extension. It is intentionally not part of the photo
# quick-start path.
# [extensions.todo]
# source_root = "~/Documents/ToDo"
# target_root = "~/Library/CloudStorage/OneDrive-Personal/ToDo"
# review_root = "~/Library/CloudStorage/OneDrive-Personal/ToDo_Review"
"""


class ConfigError(ValueError):
    """Raised when a local configuration is missing or violates the schema."""


@dataclass(frozen=True)
class PhotoStewardConfig:
    path: Path
    library_path: Path
    database_path: Path
    mount_root: Path
    photos_root: Path
    quarantine_root: Path
    receipts_root: Path
    expected_filesystem: str
    state_dir: Path
    cache_dir: Path
    state_db: Path
    status_dir: Path
    stage_dir: Path
    onedrive_root: Path | None
    todo_source_root: Path | None
    todo_target_root: Path | None
    todo_review_root: Path | None

    def cli_defaults(self) -> dict[str, Path | str | None]:
        return {
            "library_path": self.library_path,
            "db_path": self.database_path,
            "nas_mount_root": self.mount_root,
            "nas_root": self.photos_root,
            "deleted_root": self.quarantine_root,
            "logs_root": self.receipts_root,
            "state_db": self.state_db,
            "status_dir": self.status_dir,
            "stage_dir": self.stage_dir,
            "folder_logs_root": self.state_dir / "folder_sync_logs",
            "google_review_logs_root": self.state_dir / "google_review_logs",
            "expected_nas_filesystem": self.expected_filesystem,
            "onedrive_root": self.onedrive_root,
            "source_root": self.todo_source_root,
            "target_root": self.todo_target_root,
            "review_root": self.todo_review_root,
        }

    def summary(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "config_path": str(self.path),
            "photos_library": str(self.library_path),
            "mirror_mount_root": str(self.mount_root),
            "mirror_photos_root": str(self.photos_root),
            "runtime_state_dir": str(self.state_dir),
            "backup_configured": self.onedrive_root is not None,
            "todo_extension_configured": self.todo_source_root is not None,
        }


def default_config_path(home: Path | None = None) -> Path:
    user_home = Path.home() if home is None else home
    return user_home / "Library" / "Application Support" / APP_NAME / "config.toml"


def active_config_path_file(home: Path | None = None) -> Path:
    return default_config_path(home).with_name("active-config-path")


def resolve_config_path(explicit_path: Path | None = None) -> Path:
    if explicit_path is not None:
        return _expand_path(explicit_path, "--config")
    for environment_name in (CONFIG_ENV_VAR, LEGACY_CONFIG_ENV_VAR):
        environment_path = os.environ.get(environment_name)
        if environment_path:
            return _expand_path(environment_path, environment_name)
    active_path_file = active_config_path_file()
    if active_path_file.exists():
        try:
            return _expand_path(active_path_file.read_text(encoding="utf-8"), str(active_path_file))
        except OSError as exc:
            raise ConfigError(f"cannot read active configuration path {active_path_file}: {exc}") from exc
    return default_config_path()


def activate_config(path: Path) -> Path:
    resolved_config_path = _expand_path(path, "config path")
    pointer_path = active_config_path_file()
    pointer_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    pointer_path.write_text(f"{resolved_config_path}\n", encoding="utf-8")
    pointer_path.chmod(0o600)
    return pointer_path


def write_default_config(path: Path, *, force: bool = False) -> Path:
    resolved_path = _expand_path(path, "config path")
    if resolved_path.exists() and not force:
        raise ConfigError(f"configuration already exists: {resolved_path}; use --force to replace it")
    resolved_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    resolved_path.write_text(DEFAULT_CONFIG_TEMPLATE, encoding="utf-8")
    resolved_path.chmod(0o600)
    return resolved_path


def write_setup_config(
    path: Path,
    *,
    library_path: Path,
    nas_photos_path: Path,
    force: bool = False,
    mount_probe=None,
) -> Path:
    """Create the minimal private profile used by the first-run App wizard."""
    resolved_path = _expand_path(path, "config path")
    library = _expand_path(library_path, "photos library")
    nas_photos = _expand_path(nas_photos_path, "NAS photos directory")
    if not library.exists() or not library.is_dir():
        raise ConfigError(f"Photos library is not a readable directory: {library}")
    if not nas_photos.exists() or not nas_photos.is_dir():
        raise ConfigError(f"NAS photos directory is not a readable directory: {nas_photos}")

    probe = mount_probe or inspect_mount
    try:
        mount = probe(
            nas_photos,
            expected_filesystems=(),
            require_writable=True,
        )
    except Exception as exc:  # noqa: BLE001
        raise ConfigError(f"NAS directory setup check failed: {exc}") from exc

    mount_root = Path(mount["mount_point"])
    expected_filesystem = str(mount["filesystem"])
    _ensure_within_mount(nas_photos, mount_root, "mirror.photos_root")
    quarantine_root = mount_root / "PhotoSteward_Quarantine"
    receipts_root = mount_root / "PhotoSteward_Receipts"
    state_dir = default_config_path().parent / "state"
    cache_dir = Path.home() / "Library" / "Caches" / APP_NAME
    payload = f"""# Photo Steward local configuration.
# Generated by the Photo Steward first-run setup wizard.
schema_version = 1

[photos]
library_path = {_toml_string(library)}

[mirror]
mount_root = {_toml_string(mount_root)}
photos_root = {_toml_string(nas_photos)}
quarantine_root = {_toml_string(quarantine_root)}
receipts_root = {_toml_string(receipts_root)}
expected_filesystem = {_toml_string(expected_filesystem)}

[runtime]
state_dir = {_toml_string(state_dir)}
cache_dir = {_toml_string(cache_dir)}
"""
    if resolved_path.exists() and not force:
        raise ConfigError(f"configuration already exists: {resolved_path}; use --force to replace it")
    resolved_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    resolved_path.write_text(payload, encoding="utf-8")
    resolved_path.chmod(0o600)
    activate_config(resolved_path)
    return resolved_path


def _toml_string(value: Path | str) -> str:
    # JSON string escaping is valid for the basic TOML string form.
    import json

    return json.dumps(str(value), ensure_ascii=False)


def load_config(path: Path) -> PhotoStewardConfig:
    resolved_path = _expand_path(path, "config path")
    if not resolved_path.exists():
        raise ConfigError(
            f"configuration not found: {resolved_path}; run 'icloud-photo-sync config init' first"
        )
    if not resolved_path.is_file():
        raise ConfigError(f"configuration is not a file: {resolved_path}")

    try:
        payload = tomllib.loads(resolved_path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(f"cannot read configuration {resolved_path}: {exc}") from exc

    _validate_no_secrets(payload)
    _validate_known_keys(payload, TOP_LEVEL_KEYS, "root")
    schema_version = payload.get("schema_version")
    if schema_version != SCHEMA_VERSION:
        raise ConfigError(f"unsupported schema_version {schema_version!r}; expected {SCHEMA_VERSION}")

    photos = _table(payload, "photos")
    mirror = _table(payload, "mirror")
    runtime = _table(payload, "runtime")
    backup = _optional_table(payload, "backup")
    extensions = _optional_table(payload, "extensions")
    todo = _optional_table(extensions, "todo") if extensions is not None else None
    _validate_known_keys(photos, TABLE_KEYS["photos"], "photos")
    _validate_known_keys(mirror, TABLE_KEYS["mirror"], "mirror")
    _validate_known_keys(runtime, TABLE_KEYS["runtime"], "runtime")
    if backup is not None:
        _validate_known_keys(backup, TABLE_KEYS["backup"], "backup")
    if extensions is not None:
        _validate_known_keys(extensions, TABLE_KEYS["extensions"], "extensions")
    if todo is not None:
        _validate_known_keys(todo, TABLE_KEYS["extensions.todo"], "extensions.todo")

    library_path = _path_value(photos, "library_path", "photos.library_path")
    database_path = _optional_path_value(photos, "database_path", "photos.database_path")
    if database_path is None:
        database_path = library_path / "database" / "Photos.sqlite"

    mount_root = _path_value(mirror, "mount_root", "mirror.mount_root")
    photos_root = _path_value(mirror, "photos_root", "mirror.photos_root")
    quarantine_root = _path_value(mirror, "quarantine_root", "mirror.quarantine_root")
    receipts_root = _path_value(mirror, "receipts_root", "mirror.receipts_root")
    expected_filesystem = _string_value(mirror, "expected_filesystem", "mirror.expected_filesystem")
    _ensure_within_mount(photos_root, mount_root, "mirror.photos_root")
    _ensure_within_mount(quarantine_root, mount_root, "mirror.quarantine_root")
    _ensure_within_mount(receipts_root, mount_root, "mirror.receipts_root")

    state_dir = _path_value(runtime, "state_dir", "runtime.state_dir")
    cache_dir = _path_value(runtime, "cache_dir", "runtime.cache_dir")
    state_db = _optional_path_value(runtime, "state_db", "runtime.state_db") or state_dir / "state.sqlite3"
    status_dir = _optional_path_value(runtime, "status_dir", "runtime.status_dir") or state_dir / "status"
    stage_dir = _optional_path_value(runtime, "stage_dir", "runtime.stage_dir") or cache_dir / "stage"

    onedrive_root = None
    if backup is not None and "onedrive_root" in backup:
        onedrive_root = _path_value(backup, "onedrive_root", "backup.onedrive_root")

    todo_source_root = todo_target_root = todo_review_root = None
    if todo is not None:
        todo_source_root = _path_value(todo, "source_root", "extensions.todo.source_root")
        todo_target_root = _path_value(todo, "target_root", "extensions.todo.target_root")
        todo_review_root = _path_value(todo, "review_root", "extensions.todo.review_root")

    return PhotoStewardConfig(
        path=resolved_path,
        library_path=library_path,
        database_path=database_path,
        mount_root=mount_root,
        photos_root=photos_root,
        quarantine_root=quarantine_root,
        receipts_root=receipts_root,
        expected_filesystem=expected_filesystem,
        state_dir=state_dir,
        cache_dir=cache_dir,
        state_db=state_db,
        status_dir=status_dir,
        stage_dir=stage_dir,
        onedrive_root=onedrive_root,
        todo_source_root=todo_source_root,
        todo_target_root=todo_target_root,
        todo_review_root=todo_review_root,
    )


def _table(payload: dict[str, Any], name: str) -> dict[str, Any]:
    value = payload.get(name)
    if not isinstance(value, dict):
        raise ConfigError(f"missing table [{name}]")
    return value


def _optional_table(payload: dict[str, Any] | None, name: str) -> dict[str, Any] | None:
    if payload is None:
        return None
    value = payload.get(name)
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ConfigError(f"[{name}] must be a table")
    return value


def _string_value(table: dict[str, Any], key: str, label: str) -> str:
    value = table.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{label} must be a non-empty string")
    return value.strip()


def _path_value(table: dict[str, Any], key: str, label: str) -> Path:
    return _expand_path(_string_value(table, key, label), label)


def _optional_path_value(table: dict[str, Any], key: str, label: str) -> Path | None:
    if key not in table:
        return None
    return _path_value(table, key, label)


def _expand_path(value: str | Path, label: str) -> Path:
    raw_value = str(value).strip()
    if not raw_value:
        raise ConfigError(f"{label} must not be empty")
    if "<" in raw_value or ">" in raw_value:
        raise ConfigError(f"{label} still contains a template placeholder")
    expanded = os.path.expandvars(os.path.expanduser(raw_value))
    path = Path(expanded)
    if not path.is_absolute():
        raise ConfigError(f"{label} must be an absolute path")
    return path


def _ensure_within_mount(path: Path, mount_root: Path, label: str) -> None:
    try:
        path.relative_to(mount_root)
    except ValueError as exc:
        raise ConfigError(f"{label} must be below mirror.mount_root ({mount_root})") from exc


def _validate_no_secrets(value: Any, path: tuple[str, ...] = ()) -> None:
    if isinstance(value, dict):
        for key, nested_value in value.items():
            normalized_key = key.lower()
            if normalized_key in SENSITIVE_KEYWORDS:
                raise ConfigError(
                    f"{'.'.join((*path, key))} must not be stored in config.toml; use Keychain or the adapter's own store"
                )
            _validate_no_secrets(nested_value, (*path, key))


def _validate_known_keys(table: dict[str, Any], allowed_keys: set[str], label: str) -> None:
    unknown_keys = sorted(set(table) - allowed_keys)
    if unknown_keys:
        raise ConfigError(f"unknown key(s) in [{label}]: {', '.join(unknown_keys)}")

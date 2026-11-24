"""Photo Steward's lightweight local runtime, CLI, and Skill activation owner.

Desktop macOS App installation and in-app automatic updates are owned by the
signed macOS App bundle and Sparkle 2; this module never downloads or replaces
application bundles and never reads or changes photo data.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import tempfile
import uuid

PACKAGE_ID = "photo-steward"
BUNDLE_ID = "com.photosteward.photo-center"
APP_NAME = "Photo Steward.app"
RUNTIME_RELATIVE = Path("Contents/Resources/PhotoStewardRuntime")
LEGACY_WRAPPER = '#!/bin/zsh\nset -euo pipefail\nRUNTIME_ROOT="$HOME/Library/Application Support/Photo Steward/runtime/current"\nexec "$RUNTIME_ROOT/scripts/icloud-photo-sync" "$@"\n'
WRAPPER = '#!/bin/zsh\nset -euo pipefail\nRUNTIME_ROOT="${0:A:h:h:h}/Library/Application Support/Photo Steward/runtime/current"\nexec "$RUNTIME_ROOT/scripts/icloud-photo-sync" "$@"\n'


class InstallationError(ValueError):
    pass


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _identity(location: Path) -> str:
    return f"{PACKAGE_ID}:{_digest(str(location.resolve()).encode())[:24]}"


def _revision(value: dict) -> str:
    return _digest(json.dumps(value, sort_keys=True).encode())


def _runtime_base(home: Path) -> Path:
    return home / "Library/Application Support/Photo Steward/runtime"


def _read(path: Path, limit: int = 262144) -> bytes:
    if not path.is_file() or path.stat().st_size > limit:
        raise InstallationError("installation_evidence_invalid")
    return path.read_bytes()


def _source(root: Path) -> dict:
    manifest = json.loads(_read(root / "opl-package.json"))
    if manifest.get("package_id") != PACKAGE_ID or not isinstance(manifest.get("version"), str):
        raise InstallationError("source_identity_invalid")
    if not (root / "tools/icloud_photo_sync/cli.py").is_file() or not (root / "scripts/icloud-photo-sync").is_file():
        raise InstallationError("source_entrypoint_missing")
    return manifest


def _app(app: Path) -> dict:
    plist_bytes = _read(app / "Contents/Info.plist")
    info = plistlib.loads(plist_bytes)
    if info.get("CFBundleIdentifier") != BUNDLE_ID or info.get("CFBundleExecutable") != "PhotoCenterMenuBar":
        raise InstallationError("bundle_identity_invalid")
    executable = app / "Contents/MacOS/PhotoCenterMenuBar"
    if not executable.is_file() or not os.access(executable, os.X_OK):
        raise InstallationError("bundle_entrypoint_missing")
    version = info.get("CFBundleShortVersionString")
    if not isinstance(version, str) or not re.fullmatch(r"\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.-]+)?", version):
        raise InstallationError("bundle_version_invalid")
    runtime = app / RUNTIME_RELATIVE
    runtime_digest = _read(runtime / ".runtime-manifest", 1024).decode().strip()
    if not re.fullmatch(r"[a-f0-9]{64}", runtime_digest) or not (runtime / "scripts/icloud-photo-sync").is_file():
        raise InstallationError("bundle_runtime_invalid")
    return {
        "version": version,
        "mode": "development" if info.get("PhotoStewardDevelopmentBuild") is True else "release",
        "runtime_digest": runtime_digest,
        "bundle_digest": _digest(plist_bytes),
        "executable_digest": _digest(executable.read_bytes()),
    }


def _existing_apps(home: Path, app_paths: list[Path]) -> list[Path]:
    selected = []
    try:
        receipt = json.loads(_read(_runtime_base(home) / "current/.installation.json"))
        if isinstance(receipt.get("location"), str):
            selected.append(Path(receipt["location"]))
    except (OSError, ValueError):
        pass
    return list(
        dict.fromkeys(
            path.absolute()
            for path in [
                home / "Applications" / APP_NAME,
                Path("/Applications") / APP_NAME,
                home / "Applications/Photo Steward Development" / APP_NAME,
                *app_paths,
                *selected,
            ]
        )
    )


def _linked_source(home: Path) -> Path | None:
    cli = home / ".local/bin/photo-steward"
    if cli.is_symlink():
        root = cli.resolve().parent.parent
        try:
            root.relative_to(_runtime_base(home))
            return None
        except ValueError:
            pass
        try:
            _source(root)
            return root
        except (OSError, ValueError):
            pass
    current = _runtime_base(home) / "current"
    if current.is_symlink():
        try:
            root = current.resolve()
            try:
                root.relative_to(_runtime_base(home))
                return None
            except ValueError:
                pass
            _source(root)
            return root
        except (OSError, ValueError):
            pass
    return None


def _development_sources(home: Path) -> list[Path]:
    linked = _linked_source(home)
    sources = [linked] if linked else []
    directory = _runtime_base(home) / "development"
    if directory.is_dir():
        for link in sorted(directory.iterdir()):
            if link.is_symlink():
                try:
                    source = link.resolve()
                    _source(source)
                    if link.name == _identity(source).split(":")[-1]:
                        sources.append(source)
                except (OSError, ValueError):
                    pass
    return list(dict.fromkeys(sources))


def _owned_cli(path: Path) -> bool:
    if not path.exists() and not path.is_symlink():
        return True
    try:
        if path.is_symlink():
            root = path.resolve().parent.parent
            _source(root)
            return path.resolve() == root / "scripts/icloud-photo-sync"
        return _read(path, 16384).decode().strip() in {WRAPPER.strip(), LEGACY_WRAPPER.strip()}
    except (OSError, ValueError):
        return False


def _skill_fingerprint(path: Path) -> str:
    entries = []
    for child in sorted(path.rglob("*")):
        if child.is_file() and "__pycache__" not in child.parts:
            entries.append((str(child.relative_to(path)), _digest(child.read_bytes())))
    return _revision({"files": entries})


def _skill_owned(path: Path, candidates: list[Path]) -> bool:
    if not path.exists() and not path.is_symlink():
        return True
    if path.is_symlink():
        return any(path.resolve() == candidate.resolve() for candidate in candidates)
    return path.is_dir() and any(
        candidate.is_dir() and _skill_fingerprint(path) == _skill_fingerprint(candidate)
        for candidate in candidates
    )


def _read_if_present(path: Path) -> bytes:
    try:
        return _read(path)
    except (OSError, ValueError):
        return b""


def inspect(home: Path, codex_home: Path, app_paths: list[Path] | None = None) -> dict:
    home, codex_home = home.absolute(), codex_home.absolute()
    rows = []
    current = _runtime_base(home) / "current"
    cli = home / ".local/bin/photo-steward"
    wrapper_current = cli.is_file() and not cli.is_symlink() and _owned_cli(cli)
    links = {
        str(path): str(path.resolve()) if path.is_symlink() else _digest(_read_if_present(path))
        for path in [cli, home / ".local/bin/icloud-photo-sync"]
    }
    links["runtime"] = str(current.resolve()) if current.is_symlink() else None
    for app in _existing_apps(home, app_paths or []):
        try:
            facts = _app(app)
        except (OSError, ValueError, plistlib.InvalidFileException):
            continue
        active = False
        if current.is_symlink() and wrapper_current:
            try:
                marker = json.loads(_read(current / ".installation.json"))
                active = (
                    marker.get("installation_id") == _identity(app)
                    and marker.get("runtime_digest") == facts["runtime_digest"]
                )
            except (OSError, ValueError):
                # Legacy copies contain only a runtime digest; no app-path selection receipt.
                active = (
                    None
                    if _read_if_present(current / ".runtime-manifest").strip() == facts["runtime_digest"].encode()
                    else False
                )
        rows.append(
            {
                "installation_id": _identity(app),
                "kind": "macos_app",
                "mode": facts["mode"],
                "version": facts["version"],
                "location": str(app),
                "manager": "package_owner",
                "active": active,
                "entrypoints": {
                    "app": str(app),
                    "cli": str(cli),
                    "skill": str(codex_home / "skills/photo-steward"),
                },
                "revision": _revision({"location": str(app), "links": links, **facts}),
                "evidence": {
                    "bundle_id": BUNDLE_ID,
                    "info_plist": str(app / "Contents/Info.plist"),
                    "runtime_digest": facts["runtime_digest"],
                },
                "supported_actions": ["inspect", "activate"],
            }
        )
    for source in _development_sources(home):
        manifest = _source(source)
        active = (cli.is_symlink() and cli.resolve() == source / "scripts/icloud-photo-sync") or (
            wrapper_current and current.is_symlink() and current.resolve() == source
        )
        rows.append(
            {
                "installation_id": _identity(source),
                "kind": "source_link",
                "mode": "development",
                "version": manifest["version"],
                "location": str(source),
                "manager": "package_owner",
                "active": active,
                "entrypoints": {
                    "cli": str(cli),
                    "skill": str(codex_home / "skills/photo-steward"),
                },
                "revision": _revision(
                    {
                        "source": str(source),
                        "manifest": _digest(_read(source / "opl-package.json")),
                        "links": links,
                    }
                ),
                "evidence": {
                    "descriptor": str(source / "opl-package.json"),
                    "cli_target": str(cli.resolve()),
                },
                "supported_actions": ["inspect", "activate", "unlink"],
            }
        )
    active_rows = [row for row in rows if row["active"] is True]
    selection_status = (
        "active"
        if active_rows
        else "unknown"
        if any(row["active"] is None for row in rows)
        else "inactive"
    )
    if len(active_rows) == 1:
        row = active_rows[0]
        selected_runtime = Path(row["location"]) if row["kind"] == "source_link" else current.resolve()
        skill = codex_home / "skills/photo-steward"
        pointer_disagrees = current.is_symlink() and current.resolve() != selected_runtime
        skill_disagrees = (skill.exists() or skill.is_symlink()) and not _skill_owned(
            skill, [selected_runtime / "skills/photo-steward"]
        )
        legacy_alias = home / ".local/bin/icloud-photo-sync"
        alias_disagrees = legacy_alias.exists() and (
            not _owned_cli(legacy_alias)
            or (
                legacy_alias.is_symlink()
                and legacy_alias.resolve() != selected_runtime / "scripts/icloud-photo-sync"
            )
        )
        if pointer_disagrees or skill_disagrees or alias_disagrees:
            row["active"] = None
            selection_status = "conflict"
    if len(active_rows) > 1:
        selection_status = "conflict"
        for row in active_rows:
            row["active"] = None
    return {
        "schema_version": "photo-steward.installations.v1",
        "package_id": PACKAGE_ID,
        "display_name": "Photo Steward",
        "software_type": "application",
        "installations": rows,
        "active_installation_id": next(
            (row["installation_id"] for row in rows if row["active"] is True), None
        ),
        "active_installation_status": selection_status,
        "data_preserved": [
            str(home / "Library/Application Support/Photo Steward/config.toml"),
            "Photos library",
            "NAS mirror",
            "plans and receipts",
        ],
    }


@contextmanager
def _lock(home: Path):
    root = _runtime_base(home)
    root.mkdir(parents=True, exist_ok=True)
    lock = root / ".installation.lock"
    try:
        lock.mkdir()
    except FileExistsError as exc:
        raise InstallationError("installation_busy") from exc
    try:
        yield
    finally:
        lock.rmdir()


def _select(home: Path, codex_home: Path, installation_id: str, expected_revision: str, app_paths: list[Path]) -> dict:
    row = next(
        (
            row
            for row in inspect(home, codex_home, app_paths)["installations"]
            if row["installation_id"] == installation_id
        ),
        None,
    )
    if row is None:
        raise InstallationError("installation_not_found")
    if row["revision"] != expected_revision:
        raise InstallationError("installation_revision_conflict")
    return row


def _replace_link(link: Path, destination: Path) -> None:
    link.parent.mkdir(parents=True, exist_ok=True)
    temporary = link.with_name(f".{link.name}.{uuid.uuid4().hex}")
    temporary.symlink_to(destination)
    os.replace(temporary, link)


def _activate(row: dict, home: Path, codex_home: Path, app_paths: list[Path]) -> None:
    location = Path(row["location"])
    base = _runtime_base(home)
    source = location if row["kind"] == "source_link" else location / RUNTIME_RELATIVE
    current = base / "current"
    if current.exists() and not current.is_symlink():
        raise InstallationError("runtime_pointer_not_owned")
    wrappers = [home / ".local/bin" / name for name in ["photo-steward", "icloud-photo-sync"]]
    if not all(_owned_cli(wrapper) for wrapper in wrappers):
        raise InstallationError("cli_entrypoint_conflict")
    skill = codex_home / "skills/photo-steward"
    candidates = [source / "skills/photo-steward", current / "skills/photo-steward"]
    linked = _linked_source(home)
    if linked:
        candidates.append(linked / "skills/photo-steward")
    candidates.extend(app / RUNTIME_RELATIVE / "skills/photo-steward" for app in _existing_apps(home, app_paths))
    if not _skill_owned(skill, candidates):
        raise InstallationError("skill_entrypoint_conflict")
    destination = source
    if row["kind"] == "macos_app":
        facts = _app(location)
        destination = base / f"{row['version']}-{row['installation_id'].split(':')[-1]}"
        if destination.exists():
            marker = json.loads(_read(destination / ".installation.json"))
            if marker.get("installation_id") != row["installation_id"] or marker.get("runtime_digest") != facts["runtime_digest"]:
                shutil.rmtree(destination)
        if not destination.exists():
            staged = base / f".staging-{uuid.uuid4().hex}"
            try:
                shutil.copytree(source, staged, symlinks=True)
                (staged / ".installation.json").write_text(
                    json.dumps(
                        {
                            "installation_id": row["installation_id"],
                            "location": str(location),
                            "version": row["version"],
                            "runtime_digest": facts["runtime_digest"],
                        }
                    )
                )
                (staged / ".installed").write_text(f"Photo Steward {row['version']}\n")
                os.replace(staged, destination)
            finally:
                if staged.exists():
                    shutil.rmtree(staged)
    if row["kind"] == "source_link":
        _replace_link(base / "development" / row["installation_id"].split(":")[-1], source)
    with tempfile.TemporaryDirectory(prefix=".activation-", dir=base) as temporary:
        backups = []
        for index, entry in enumerate([*wrappers, skill]):
            backup = Path(temporary) / str(index)
            if entry.is_symlink():
                backup.symlink_to(os.readlink(entry))
            elif entry.is_dir():
                shutil.copytree(entry, backup)
            elif entry.is_file():
                shutil.copy2(entry, backup)
            backups.append((entry, backup))
        try:
            for wrapper in wrappers:
                wrapper.parent.mkdir(parents=True, exist_ok=True)
                staged_wrapper = wrapper.with_name(f".{wrapper.name}.{uuid.uuid4().hex}")
                staged_wrapper.write_text(WRAPPER)
                staged_wrapper.chmod(0o755)
                os.replace(staged_wrapper, wrapper)
            if skill.exists() and not skill.is_symlink():
                shutil.rmtree(skill)
            _replace_link(skill, current / "skills/photo-steward")
            _replace_link(current, destination)
        except OSError:
            for entry, backup in backups:
                if entry.is_dir() and not entry.is_symlink():
                    shutil.rmtree(entry)
                else:
                    entry.unlink(missing_ok=True)
                if backup.exists() or backup.is_symlink():
                    os.replace(backup, entry)
            raise


def _detach(row: dict, home: Path, codex_home: Path) -> None:
    location = Path(row["location"])
    current = _runtime_base(home) / "current"
    if row["active"] is None:
        raise InstallationError("activate_installation_to_resolve_legacy_selection")
    if row["active"] is True:
        for name in ["photo-steward", "icloud-photo-sync"]:
            wrapper = home / ".local/bin" / name
            if not _owned_cli(wrapper):
                raise InstallationError("cli_entrypoint_conflict")
        skill = codex_home / "skills/photo-steward"
        if skill.is_symlink() and skill.resolve() in [
            (current / "skills/photo-steward").resolve(),
            (location / "skills/photo-steward").resolve(),
        ]:
            skill.unlink()
        for name in ["photo-steward", "icloud-photo-sync"]:
            (home / ".local/bin" / name).unlink(missing_ok=True)
        if current.is_symlink():
            current.unlink()


def configure_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--home",
        type=Path,
        default=Path(os.environ.get("PHOTO_STEWARD_INSTALLATION_HOME") or str(Path.home())),
        help="Installation owner home; use an isolated directory for verification",
    )
    parser.add_argument("--codex-home", type=Path, default=None)
    commands = parser.add_subparsers(dest="installation_action", required=True)
    for action in ["inspect", "activate", "unlink", "link", "prepare"]:
        command = commands.add_parser(action)
        command.add_argument("--json", action="store_true")
        command.add_argument("--app-path", type=Path, action="append", default=[])
        if action == "link":
            command.add_argument("--source", type=Path, required=True)
        elif action in {"activate", "unlink"}:
            command.add_argument("--installation-id", required=True)
            command.add_argument("--expected-revision", required=True)


def execute(args: argparse.Namespace) -> dict:
    home = args.home.absolute()
    codex_home = (
        args.codex_home
        or (
            Path(os.environ["CODEX_HOME"])
            if os.environ.get("CODEX_HOME") and home == Path.home()
            else home / ".codex"
        )
    ).absolute()
    if args.installation_action == "inspect":
        return inspect(home, codex_home, args.app_path)
    with _lock(home):
        action = args.installation_action
        if action == "prepare":
            snapshot = inspect(home, codex_home, args.app_path)
            selected = next((row for row in snapshot["installations"] if row["active"] is True), None)
            if selected is None and snapshot["active_installation_status"] == "conflict":
                raise InstallationError("choose_active_installation_in_software_center")
            if selected is None:
                selected = next(
                    (
                        row
                        for row in snapshot["installations"]
                        if row["kind"] == "macos_app" and Path(row["location"]) in args.app_path
                    ),
                    None,
                )
            if selected is None:
                raise InstallationError("installation_not_found")
            _activate(selected, home, codex_home, args.app_path)
        elif action == "link":
            source = args.source.resolve()
            manifest = _source(source)
            row = {
                "kind": "source_link",
                "mode": "development",
                "location": str(source),
                "version": manifest["version"],
                "installation_id": _identity(source),
            }
            _activate(row, home, codex_home, args.app_path)
        elif action in {"activate", "unlink"}:
            row = _select(home, codex_home, args.installation_id, args.expected_revision, args.app_path)
            if action == "activate":
                _activate(row, home, codex_home, args.app_path)
            else:
                if row["kind"] != "source_link":
                    raise InstallationError("development_installation_required")
                _detach(row, home, codex_home)
                (_runtime_base(home) / "development" / row["installation_id"].split(":")[-1]).unlink(missing_ok=True)
        return inspect(home, codex_home, args.app_path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="photo-steward installation")
    configure_parser(parser)
    if argv == ["--stdin"]:
        import sys

        try:
            payload = json.loads(sys.stdin.read(65537))
            if not isinstance(payload, dict) or set(payload) - {
                "package_id",
                "operation",
                "installation_id",
                "expected_revision",
                "source",
            }:
                raise InstallationError("installation_request_invalid")
            if payload.get("package_id") != PACKAGE_ID or payload.get("operation") not in {
                "inspect",
                "activate",
                "unlink",
                "link",
            }:
                raise InstallationError("installation_request_invalid")
            argv = [payload["operation"], "--json"]
            for field in ["installation_id", "expected_revision", "source"]:
                if field in payload:
                    if not isinstance(payload[field], str) or not payload[field] or payload[field].startswith("-"):
                        raise InstallationError("installation_request_invalid")
                    argv.extend(["--" + field.replace("_", "-"), payload[field]])
        except (ValueError, OSError) as exc:
            print(json.dumps({"status": "rejected", "reason": str(exc)}))
            return 2
    args = parser.parse_args(argv)
    try:
        result = execute(args)
    except (OSError, ValueError) as exc:
        print(
            json.dumps(
                {
                    "schema_version": "photo-steward.installations.v1",
                    "status": "rejected",
                    "reason": str(exc),
                }
            )
        )
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0

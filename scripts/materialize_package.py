#!/usr/bin/env python3
"""Synchronize the portable Photo Steward carrier and content lock."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path

from _opl_package_content_lock import content_lock


ROOT = Path(__file__).resolve().parents[1]
CARRIER = ROOT / "plugins/photo-steward"


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def materialize(*, check: bool = False) -> bool:
    root_manifest = json.loads((ROOT / "opl-package.json").read_text())
    carrier_manifest_path = CARRIER / "opl-package.json"
    copied = ["app-contribution-adapter.json", "scripts/manage_installation.py", "tools/icloud_photo_sync/installation.py"]
    copied.extend(str(path.relative_to(ROOT)) for path in (ROOT / "skills/photo-steward").rglob("*") if path.is_file() and "__pycache__" not in path.parts)
    if not check:
        shutil.copyfile(ROOT / "app-contribution-adapter.json", CARRIER / "app-contribution-adapter.json")
        shutil.copytree(
            ROOT / "skills/photo-steward",
            CARRIER / "skills/photo-steward",
            dirs_exist_ok=True,
        )
        for relative in ["scripts/manage_installation.py", "tools/icloud_photo_sync/installation.py"]:
            destination = CARRIER / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, destination)
    paths = sorted(
        str(path.relative_to(CARRIER))
        for path in CARRIER.rglob("*")
        if path.is_file()
        and "__pycache__" not in path.parts
        and path.name != "opl-package.json"
    )
    lock = content_lock(CARRIER, paths)
    carrier_manifest = (
        json.loads(carrier_manifest_path.read_text())
        if carrier_manifest_path.is_file()
        else {}
    )
    if check:
        return (
            root_manifest.get("content_lock") == lock
            and carrier_manifest == root_manifest
            and all((CARRIER / relative).is_file() and (CARRIER / relative).read_bytes() == (ROOT / relative).read_bytes() for relative in copied)
        )
    root_manifest["content_lock"] = lock
    _write_json(carrier_manifest_path, root_manifest)
    _write_json(ROOT / "opl-package.json", root_manifest)
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--framework-root", type=Path, help="Verify the generated content-lock helper against Framework source")
    args = parser.parse_args()
    if args.framework_root:
        subprocess.run([
            "node", str(args.framework_root / "scripts/materialize-python-support.mjs"),
            "--module", "package_content_lock", "--target",
            str(Path(__file__).with_name("_opl_package_content_lock.py")), "--check",
        ], check=True)
    valid = materialize(check=args.check)
    print(json.dumps({"status": "passed" if valid else "stale"}))
    return 0 if valid else 2


if __name__ == "__main__":
    raise SystemExit(main())

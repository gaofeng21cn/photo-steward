#!/usr/bin/env python3
"""Synchronize the portable Photo Steward carrier and content lock."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CARRIER = ROOT / "plugins/photo-steward"


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _content_lock(paths: list[str]) -> dict[str, object]:
    digest = hashlib.sha256()
    for relative in paths:
        encoded = relative.encode("utf-8")
        body = (CARRIER / relative).read_bytes()
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
        digest.update(len(body).to_bytes(8, "big"))
        digest.update(body)
    return {
        "algorithm": "sha256",
        "canonicalization": "ordered_path_length_file_length_bytes",
        "paths": paths,
        "digest": f"sha256:{digest.hexdigest()}",
    }


def materialize(*, check: bool = False) -> bool:
    root_manifest = json.loads((ROOT / "opl-package.json").read_text())
    carrier_manifest_path = CARRIER / "opl-package.json"
    if not check:
        shutil.copyfile(ROOT / "app-contribution-adapter.json", CARRIER / "app-contribution-adapter.json")
        shutil.copytree(
            ROOT / "skills/photo-steward",
            CARRIER / "skills/photo-steward",
            dirs_exist_ok=True,
        )
    paths = sorted(
        str(path.relative_to(CARRIER))
        for path in CARRIER.rglob("*")
        if path.is_file()
        and "__pycache__" not in path.parts
        and path.name != "opl-package.json"
    )
    lock = _content_lock(paths)
    root_manifest["content_lock"] = lock
    carrier_manifest = (
        json.loads(carrier_manifest_path.read_text())
        if carrier_manifest_path.is_file()
        else {}
    )
    carrier_manifest["content_lock"] = lock
    if check:
        return (
            root_manifest.get("content_lock") == lock
            and carrier_manifest == root_manifest
        )
    _write_json(carrier_manifest_path, root_manifest)
    _write_json(ROOT / "opl-package.json", root_manifest)
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    valid = materialize(check=args.check)
    print(json.dumps({"status": "passed" if valid else "stale"}))
    return 0 if valid else 2


if __name__ == "__main__":
    raise SystemExit(main())

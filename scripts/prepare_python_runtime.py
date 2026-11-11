#!/usr/bin/env python3
"""Extract and relocate the pinned official universal2 Python; never install it."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
MACHO_MAGIC = {b"\xfe\xed\xfa\xce", b"\xce\xfa\xed\xfe", b"\xfe\xed\xfa\xcf", b"\xcf\xfa\xed\xfe", b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca", b"\xca\xfe\xba\xbf", b"\xbf\xba\xfe\xca"}


def macho_files(root: Path):
    for file in root.rglob("*"):
        if file.is_symlink() or not file.is_file():
            continue
        with file.open("rb") as stream:
            if stream.read(4) in MACHO_MAGIC:
                yield file


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    profile = json.loads((ROOT / "config/python-runtime.json").read_text())
    cache = ROOT / "tmp/python-runtime"
    cache.mkdir(parents=True, exist_ok=True)
    archive = cache / Path(profile["url"]).name
    if not archive.exists():
        with urlopen(profile["url"], timeout=60) as response, archive.open("wb") as stream:
            shutil.copyfileobj(response, stream)
    if hashlib.sha256(archive.read_bytes()).hexdigest() != profile["sha256"]:
        raise ValueError("Official Python installer digest mismatch")
    signature = subprocess.check_output(["/usr/sbin/pkgutil", "--check-signature", str(archive)], text=True)
    if profile["installer_identity"] not in signature or "trusted by the Apple notary service" not in signature:
        raise ValueError("Official Python installer signature or notarization could not be verified")
    extracted = cache / "extracted"
    if not extracted.exists():
        subprocess.run(["/usr/sbin/pkgutil", "--expand-full", str(archive), str(extracted)], check=True)
    source = extracted / "Python_Framework.pkg/Payload"
    destination = args.destination.absolute()
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination, symlinks=True)
    version_root = destination / "Versions" / profile["framework_version"]
    # Keep the runtime and license; developer headers, test suites and Tk are not used by Photo Steward.
    for path in [version_root / "Headers", version_root / "include", version_root / "Frameworks", version_root / "lib" / f"python{profile['framework_version']}" / "test", version_root / "lib" / f"python{profile['framework_version']}" / "site-packages"]:
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
    for path in destination.rglob("__pycache__"):
        shutil.rmtree(path)
    for path in (version_root / "lib" / f"python{profile['framework_version']}" / "lib-dynload").glob("_tkinter*.so"):
        path.unlink()
    prefix = "/Library/Frameworks/Python.framework/"
    for file in macho_files(destination):
        output = subprocess.check_output(["/usr/bin/otool", "-L", str(file)], text=True)
        references = set(re.findall(r"^\s+(" + re.escape(prefix) + r"\S+)\s+\(", output, re.MULTILINE))
        for reference in references:
            target = destination / reference.removeprefix(prefix)
            relative = os.path.relpath(target, file.parent)
            subprocess.run(["/usr/bin/install_name_tool", "-change", reference, f"@loader_path/{relative}", str(file)], check=True, capture_output=True)
        subprocess.run(["/usr/bin/codesign", "--force", "--sign", "-", str(file)], check=True, capture_output=True)
    executable = version_root / "bin" / f"python{profile['framework_version']}"
    architectures = subprocess.check_output(["/usr/bin/lipo", "-archs", str(executable)], text=True).split()
    if set(architectures) != set(profile["architectures"]):
        raise ValueError("Python runtime architecture mismatch")
    environment = {**os.environ, "PYTHONHOME": str(version_root), "PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1"}
    observed = subprocess.check_output([str(executable), "-c", "import sys,sqlite3,ssl,tomllib; print(sys.version.split()[0])"], env=environment, text=True).strip()
    if observed != profile["version"]:
        raise ValueError("Python runtime version mismatch")
    (destination.parent / "python-runtime.json").write_text(json.dumps(profile, indent=2) + "\n")
    print(destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

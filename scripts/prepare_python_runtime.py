#!/usr/bin/env python3
"""Extract and relocate the pinned official universal2 Python with universal2 osxphotos; never install it."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
MACHO_MAGIC = {
    b"\xfe\xed\xfa\xce",
    b"\xce\xfa\xed\xfe",
    b"\xfe\xed\xfa\xcf",
    b"\xcf\xfa\xed\xfe",
    b"\xca\xfe\xba\xbe",
    b"\xbe\xba\xfe\xca",
    b"\xca\xfe\xba\xbf",
    b"\xbf\xba\xfe\xca",
}


def is_macho(path: Path) -> bool:
    if path.is_symlink() or not path.is_file():
        return False
    with path.open("rb") as stream:
        return stream.read(4) in MACHO_MAGIC


def macho_files(root: Path):
    for file in root.rglob("*"):
        if is_macho(file):
            yield file


def _osxphotos_requirement() -> str:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    for dep in pyproject.get("project", {}).get("dependencies", []):
        if dep.lower().startswith("osxphotos"):
            return dep
    return "osxphotos>=0.78.0"


def _host_arch() -> str:
    machine = platform.machine().lower()
    if machine in {"arm64", "aarch64"}:
        return "arm64"
    if machine in {"x86_64", "amd64"}:
        return "x86_64"
    raise ValueError(f"Unsupported macOS architecture: {machine}")


def _pip_platforms_for_arch(arch: str) -> list[str]:
    if arch == "arm64":
        return [
            "macosx_15_0_arm64",
            "macosx_14_0_arm64",
            "macosx_13_0_arm64",
            "macosx_12_0_arm64",
            "macosx_11_0_arm64",
            "macosx_11_0_universal2",
            "macosx_10_9_universal2",
        ]
    return [
        "macosx_15_0_x86_64",
        "macosx_14_0_x86_64",
        "macosx_13_0_x86_64",
        "macosx_12_0_x86_64",
        "macosx_11_0_x86_64",
        "macosx_10_15_x86_64",
        "macosx_10_14_x86_64",
        "macosx_10_9_x86_64",
        "macosx_11_0_universal2",
        "macosx_10_9_universal2",
    ]


def _install_native_wheels(requirement: str, python_executable: Path, framework_version: str, target_dir: Path) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    uv_bin = shutil.which("uv")
    if uv_bin:
        subprocess.run(
            [
                uv_bin,
                "pip",
                "install",
                "--target",
                str(target_dir),
                "--python",
                str(python_executable),
                "--only-binary",
                ":all:",
                requirement,
            ],
            check=True,
        )
        return

    command = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--no-user",
        "--target",
        str(target_dir),
        "--python-version",
        framework_version,
        "--implementation",
        "cp",
        "--only-binary",
        ":all:",
    ]
    for plat in _pip_platforms_for_arch(_host_arch()):
        command.extend(["--platform", plat])
    command.append(requirement)
    subprocess.run(command, check=True)


def _install_peer_arch_wheels(
    specs: list[str],
    framework_version: str,
    peer_arch: str,
    target_dir: Path,
) -> None:
    if not specs:
        return
    target_dir.mkdir(parents=True, exist_ok=True)
    uv_bin = shutil.which("uv")
    if uv_bin:
        uv_platform = "aarch64-apple-darwin" if peer_arch == "arm64" else "x86_64-apple-darwin"
        subprocess.run(
            [
                uv_bin,
                "pip",
                "install",
                "--no-deps",
                "--target",
                str(target_dir),
                "--python-version",
                framework_version,
                "--python-platform",
                uv_platform,
                "--only-binary",
                ":all:",
                *specs,
            ],
            check=True,
        )
        return

    command = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--no-user",
        "--no-deps",
        "--target",
        str(target_dir),
        "--python-version",
        framework_version,
        "--implementation",
        "cp",
        "--only-binary",
        ":all:",
    ]
    for plat in _pip_platforms_for_arch(peer_arch):
        command.extend(["--platform", plat])
    command.extend(specs)
    subprocess.run(command, check=True)


def _owners_of_files(site_dir: Path, rel_paths: set[str]) -> list[str]:
    """Map relative paths inside site-packages back to pinned Name==Version specs via .dist-info/RECORD."""
    specs: set[str] = set()
    for dist_info in sorted(site_dir.glob("*.dist-info")):
        record_file = dist_info / "RECORD"
        metadata_file = dist_info / "METADATA"
        if not record_file.is_file() or not metadata_file.is_file():
            continue
        recorded = {line.split(",", 1)[0] for line in record_file.read_text(encoding="utf-8").splitlines() if line}
        if not (recorded & rel_paths):
            continue
        name = None
        version = None
        for line in metadata_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("Name: ") and name is None:
                name = line.split(": ", 1)[1].strip()
            elif line.startswith("Version: ") and version is None:
                version = line.split(": ", 1)[1].strip()
            if name and version:
                break
        if name and version:
            specs.add(f"{name}=={version}")
    return sorted(specs)


def _prepare_universal_site_packages(
    cache: Path,
    python_executable: Path,
    framework_version: str,
) -> Path:
    requirement = _osxphotos_requirement()
    cache_key = hashlib.sha256(f"{framework_version}:{requirement}:universal2:v2".encode("utf-8")).hexdigest()[:16]
    cached_site = cache / f"site-packages-{framework_version}-{cache_key}"
    if (cached_site / "osxphotos").is_dir() and (cached_site / "Photos").is_dir() and (cached_site / "Metal").is_dir():
        return cached_site

    host_arch = _host_arch()
    peer_arch = "x86_64" if host_arch == "arm64" else "arm64"

    with tempfile.TemporaryDirectory(prefix="photo-steward-wheels-", dir=cache) as temp_root:
        temp_path = Path(temp_root)
        merged_dir = temp_path / "merged"
        peer_dir = temp_path / peer_arch

        _install_native_wheels(requirement, python_executable, framework_version, merged_dir)

        for dsym_dir in list(merged_dir.rglob("*.dSYM")):
            if dsym_dir.is_dir():
                shutil.rmtree(dsym_dir)

        single_arch_rel_paths: set[str] = set()
        for file in merged_dir.rglob("*.so"):
            if not is_macho(file):
                continue
            archs = set(subprocess.check_output(["/usr/bin/lipo", "-archs", str(file)], text=True).split())
            if archs != {"arm64", "x86_64"}:
                single_arch_rel_paths.add(str(file.relative_to(merged_dir)))

        peer_specs = _owners_of_files(merged_dir, single_arch_rel_paths)
        _install_peer_arch_wheels(peer_specs, framework_version, peer_arch, peer_dir)

        for rel_str in sorted(single_arch_rel_paths):
            host_file = merged_dir / rel_str
            peer_file = peer_dir / rel_str
            if not peer_file.is_file():
                raise ValueError(f"Missing {peer_arch} peer wheel extension for {rel_str}")
            peer_archs = set(subprocess.check_output(["/usr/bin/lipo", "-archs", str(peer_file)], text=True).split())
            if peer_arch not in peer_archs:
                raise ValueError(f"Peer extension {rel_str} missing {peer_arch}: {sorted(peer_archs)}")
            universal_tmp = host_file.with_name(f".{host_file.name}.universal2")
            subprocess.run(
                ["/usr/bin/lipo", "-create", str(host_file), str(peer_file), "-output", str(universal_tmp)],
                check=True,
            )
            universal_tmp.replace(host_file)

        for removable in (merged_dir / "bin",):
            if removable.is_dir():
                shutil.rmtree(removable)
        for cache_dir in list(merged_dir.rglob("__pycache__")):
            shutil.rmtree(cache_dir)
        for pyc_file in list(merged_dir.rglob("*.pyc")):
            pyc_file.unlink()

        if cached_site.exists():
            shutil.rmtree(cached_site)
        shutil.move(str(merged_dir), str(cached_site))

    return cached_site


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
    site_packages = version_root / "lib" / f"python{profile['framework_version']}" / "site-packages"
    # Keep the runtime and license; developer headers, test suites and Tk are not used by Photo Steward.
    for path in [
        version_root / "Headers",
        version_root / "include",
        version_root / "Frameworks",
        version_root / "lib" / f"python{profile['framework_version']}" / "test",
        site_packages,
    ]:
        if path.is_symlink():
            path.unlink()
        elif path.is_dir():
            shutil.rmtree(path)
    (destination / "Headers").unlink(missing_ok=True)

    for path in (version_root / "lib" / f"python{profile['framework_version']}" / "lib-dynload").glob("_tkinter*.so"):
        path.unlink()

    prefix = "/Library/Frameworks/Python.framework/"
    for file in macho_files(destination):
        output = subprocess.check_output(["/usr/bin/otool", "-L", str(file)], text=True)
        references = set(re.findall(r"^\s+(" + re.escape(prefix) + r"\S+)\s+\(", output, re.MULTILINE))
        for reference in references:
            target = destination / reference.removeprefix(prefix)
            relative = os.path.relpath(target, file.parent)
            subprocess.run(
                ["/usr/bin/install_name_tool", "-change", reference, f"@loader_path/{relative}", str(file)],
                check=True,
                capture_output=True,
            )
        subprocess.run(["/usr/bin/codesign", "--force", "--sign", "-", str(file)], check=True, capture_output=True)

    executable = version_root / "bin" / f"python{profile['framework_version']}"
    universal_site_packages = _prepare_universal_site_packages(cache, executable, profile["framework_version"])
    shutil.copytree(universal_site_packages, site_packages, symlinks=True)

    for path in destination.rglob("__pycache__"):
        shutil.rmtree(path)

    for file in macho_files(site_packages):
        output = subprocess.check_output(["/usr/bin/otool", "-L", str(file)], text=True)
        references = set(re.findall(r"^\s+(" + re.escape(prefix) + r"\S+)\s+\(", output, re.MULTILINE))
        for reference in references:
            target = destination / reference.removeprefix(prefix)
            relative = os.path.relpath(target, file.parent)
            subprocess.run(
                ["/usr/bin/install_name_tool", "-change", reference, f"@loader_path/{relative}", str(file)],
                check=True,
                capture_output=True,
            )
        subprocess.run(["/usr/bin/codesign", "--force", "--sign", "-", str(file)], check=True, capture_output=True)

    architectures = subprocess.check_output(["/usr/bin/lipo", "-archs", str(executable)], text=True).split()
    if set(architectures) != set(profile["architectures"]):
        raise ValueError("Python runtime architecture mismatch")
    for extension in site_packages.rglob("*.so"):
        ext_archs = set(subprocess.check_output(["/usr/bin/lipo", "-archs", str(extension)], text=True).split())
        if ext_archs != set(profile["architectures"]):
            raise ValueError(f"Extension {extension.relative_to(site_packages)} is not universal2: {sorted(ext_archs)}")

    environment = {
        **os.environ,
        "PYTHONHOME": str(version_root),
        "PYTHONNOUSERSITE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    observed = subprocess.check_output(
        [
            str(executable),
            "-c",
            "import sys, sqlite3, ssl, tomllib, osxphotos; from osxphotos import photokit; print(sys.version.split()[0])",
        ],
        env=environment,
        text=True,
    ).strip()
    if observed != profile["version"]:
        raise ValueError("Python runtime version mismatch")
    (destination.parent / "python-runtime.json").write_text(json.dumps(profile, indent=2) + "\n")
    print(destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

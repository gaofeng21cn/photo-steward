from __future__ import annotations

import os
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Iterable


WRITE_PROBE_NAME = ".icloud-photo-sync-write-probe"


class MountContractError(RuntimeError):
    pass


@dataclass(frozen=True)
class MountIdentity:
    checked_path: str
    mount_point: str
    mounted_from: str
    filesystem: str
    options: tuple[str, ...]
    readable: bool
    writable: bool

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["options"] = list(self.options)
        return payload


def parse_mount_output(output: str) -> list[tuple[str, str, str, tuple[str, ...]]]:
    records: list[tuple[str, str, str, tuple[str, ...]]] = []
    for raw_line in output.splitlines():
        body, separator, details = raw_line.rpartition(" (")
        if not separator or not details.endswith(")"):
            continue
        mounted_from, separator, mount_point = body.rpartition(" on ")
        if not separator:
            continue
        fields = tuple(part.strip() for part in details[:-1].split(",") if part.strip())
        if not fields:
            continue
        records.append((mounted_from, mount_point, fields[0], fields[1:]))
    return records


def _is_path_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def inspect_mount(
    path: Path,
    *,
    expected_filesystems: Iterable[str] = ("smbfs",),
    require_writable: bool = False,
    command_runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    mount_bin: str = "/sbin/mount",
) -> dict:
    checked_path = Path(os.path.abspath(os.path.expanduser(path)))
    proc = command_runner([mount_bin], capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise MountContractError(f"cannot inspect mounts: {proc.stderr.strip() or proc.returncode}")

    candidates = []
    for mounted_from, mount_point, filesystem, options in parse_mount_output(proc.stdout):
        candidate = Path(mount_point)
        if _is_path_within(checked_path, candidate):
            candidates.append((candidate, mounted_from, filesystem, options))
    if not candidates:
        raise MountContractError(f"path is not backed by a mounted filesystem: {checked_path}")

    mount_point, mounted_from, filesystem, options = max(candidates, key=lambda item: len(str(item[0])))
    expected = set(expected_filesystems)
    if expected and filesystem not in expected:
        raise MountContractError(
            f"unexpected filesystem for {checked_path}: {filesystem}; expected {', '.join(sorted(expected))}"
        )
    if mount_point == Path("/"):
        raise MountContractError(f"refusing local-root fallback for external path: {checked_path}")
    if not checked_path.exists():
        raise MountContractError(f"mounted path does not exist: {checked_path}")

    try:
        with os.scandir(checked_path):
            pass
    except OSError as exc:
        raise MountContractError(f"mounted path is not readable: {checked_path}: {exc}") from exc

    writable = False
    if require_writable:
        probe_path = mount_point / WRITE_PROBE_NAME
        try:
            descriptor = os.open(probe_path, os.O_WRONLY | os.O_CREAT, 0o600)
            os.close(descriptor)
        except OSError as exc:
            raise MountContractError(f"mounted filesystem is not writable: {mount_point}: {exc}") from exc
        else:
            writable = True

    return MountIdentity(
        checked_path=str(checked_path),
        mount_point=str(mount_point),
        mounted_from=mounted_from,
        filesystem=filesystem,
        options=options,
        readable=True,
        writable=writable,
    ).to_dict()

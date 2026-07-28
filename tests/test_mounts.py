import subprocess
from pathlib import Path
from stat import S_IMODE

import pytest

from tools.icloud_photo_sync.mounts import (
    WRITE_PROBE_NAME,
    MountContractError,
    inspect_mount,
    parse_mount_output,
)


MOUNT_OUTPUT = """\
/dev/disk3s5 on /System/Volumes/Data (apfs, local, journaled)
//photo-user@nas-host._smb._tcp.local/photos on /Volumes/photo-nas (smbfs, nodev, nosuid)
"""


def test_parse_mount_output_preserves_real_source_and_filesystem() -> None:
    assert parse_mount_output(MOUNT_OUTPUT)[1] == (
        "//photo-user@nas-host._smb._tcp.local/photos",
        "/Volumes/photo-nas",
        "smbfs",
        ("nodev", "nosuid"),
    )


def test_inspect_mount_returns_identity_for_path_below_mount(tmp_path: Path) -> None:
    mounted_root = tmp_path / "home"
    photos_root = mounted_root / "Photos"
    photos_root.mkdir(parents=True)
    output = f"/dev/disk3s5 on / (apfs, local)\n//user@nas/home on {mounted_root} (smbfs, nodev)\n"

    def fake_runner(command, capture_output, text, check):
        return subprocess.CompletedProcess(command, 0, stdout=output, stderr="")

    identity = inspect_mount(
        photos_root,
        require_writable=True,
        command_runner=fake_runner,
    )

    assert identity["mount_point"] == str(mounted_root)
    assert identity["mounted_from"] == "//user@nas/home"
    assert identity["filesystem"] == "smbfs"
    assert identity["readable"] is True
    assert identity["writable"] is True
    probe = mounted_root / WRITE_PROBE_NAME
    assert probe.is_file()
    assert probe.stat().st_size == 0
    assert S_IMODE(probe.stat().st_mode) == 0o600


def test_inspect_mount_reuses_write_probe_without_modifying_it(tmp_path: Path) -> None:
    mounted_root = tmp_path / "home"
    photos_root = mounted_root / "Photos"
    photos_root.mkdir(parents=True)
    probe = mounted_root / WRITE_PROBE_NAME
    probe.write_text("existing sentinel", encoding="utf-8")
    before = probe.stat()
    output = f"//user@nas/home on {mounted_root} (smbfs, nodev)\n"

    def fake_runner(command, capture_output, text, check):
        return subprocess.CompletedProcess(command, 0, stdout=output, stderr="")

    identity = inspect_mount(
        photos_root,
        require_writable=True,
        command_runner=fake_runner,
    )

    after = probe.stat()
    assert identity["writable"] is True
    assert probe.read_text(encoding="utf-8") == "existing sentinel"
    assert after.st_ino == before.st_ino
    assert after.st_mtime_ns == before.st_mtime_ns


def test_inspect_mount_rejects_local_fallback(tmp_path: Path) -> None:
    def fake_runner(command, capture_output, text, check):
        return subprocess.CompletedProcess(command, 0, stdout="/dev/disk3s5 on / (apfs, local)\n", stderr="")

    with pytest.raises(MountContractError, match="unexpected filesystem"):
        inspect_mount(tmp_path, command_runner=fake_runner)

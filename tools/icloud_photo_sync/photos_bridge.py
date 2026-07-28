from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile


@dataclass(frozen=True)
class PhotosResourceDescriptor:
    asset_local_identifier: str
    asset_uuid: str
    media_type: int
    media_subtypes: int
    creation_date: str | None
    modification_date: str | None
    resource_index: int
    resource_type: int
    original_filename: str
    uniform_type_identifier: str | None
    file_size: int | None

    @property
    def resource_key(self) -> str:
        return f"{self.asset_uuid}:{self.resource_index}:{self.original_filename}"


class PhotosBridge:
    def __init__(self, swift_source: Path, build_dir: Path) -> None:
        self.swift_source = Path(swift_source)
        self.build_dir = Path(build_dir)
        self.binary_path = self.build_dir / "photos_bridge"

    def ensure_binary(self) -> Path:
        bundled_path = os.environ.get("PHOTO_STEWARD_PHOTOS_BRIDGE")
        if bundled_path:
            candidate = Path(bundled_path).expanduser()
            if candidate.is_file() and candidate.stat().st_mode & 0o111:
                return candidate

        self.build_dir.mkdir(parents=True, exist_ok=True)
        if self.binary_path.exists() and self.binary_path.stat().st_mtime >= self.swift_source.stat().st_mtime:
            return self.binary_path

        if not self.swift_source.exists():
            raise RuntimeError(
                "Photos bridge is not available in this installation; "
                "install the Photo Steward App or use a source checkout with Xcode"
            )

        command = [
            "swiftc",
            str(self.swift_source),
            "-o",
            str(self.binary_path),
            "-framework",
            "Photos",
        ]
        try:
            proc = subprocess.run(command, capture_output=True, text=True)
        except FileNotFoundError as exc:
            raise RuntimeError(
                "Photos bridge is not bundled and swiftc is unavailable; "
                "install the Photo Steward App or use a source checkout with Xcode"
            ) from exc
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or "swiftc failed")
        return self.binary_path

    def _run(self, *args: str) -> subprocess.CompletedProcess[str]:
        binary = self.ensure_binary()
        proc = subprocess.run(
            [str(binary), *args],
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or "photos bridge failed")
        return proc

    def list_resources(self) -> list[PhotosResourceDescriptor]:
        proc = self._run("list-resources")
        resources: list[PhotosResourceDescriptor] = []
        for line in proc.stdout.splitlines():
            if not line.strip():
                continue
            payload = json.loads(line)
            resources.append(
                PhotosResourceDescriptor(
                    asset_local_identifier=payload["asset_local_identifier"],
                    asset_uuid=payload["asset_uuid"],
                    media_type=int(payload["media_type"]),
                    media_subtypes=int(payload["media_subtypes"]),
                    creation_date=payload.get("creation_date"),
                    modification_date=payload.get("modification_date"),
                    resource_index=int(payload["resource_index"]),
                    resource_type=int(payload["resource_type"]),
                    original_filename=payload["original_filename"],
                    uniform_type_identifier=payload.get("uniform_type_identifier"),
                    file_size=payload.get("file_size"),
                )
            )
        return resources

    def export_resource(self, asset_local_identifier: str, resource_index: int, output_path: Path) -> Path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        proc = self._run("export-resource", asset_local_identifier, str(resource_index), str(output_path))
        payload = json.loads(proc.stdout.strip() or "{}")
        exported = Path(payload.get("output_path", output_path))
        if not exported.exists():
            raise RuntimeError(f"exported file missing: {exported}")
        return exported

    def export_resources_batch(self, requests: list[dict]) -> dict[str, dict]:
        if not requests:
            return {}

        with NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as handle:
            json.dump(requests, handle, ensure_ascii=False)
            request_path = Path(handle.name)

        try:
            proc = self._run("export-batch", str(request_path))
        finally:
            request_path.unlink(missing_ok=True)

        results: dict[str, dict] = {}
        for line in proc.stdout.splitlines():
            if not line.strip():
                continue
            payload = json.loads(line)
            results[payload["request_id"]] = payload
        return results

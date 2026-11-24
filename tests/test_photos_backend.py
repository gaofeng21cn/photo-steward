from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools.icloud_photo_sync.photos_backend import (
    MEDIA_SUBTYPE_PHOTO_LIVE,
    MEDIA_TYPE_IMAGE,
    MEDIA_TYPE_VIDEO,
    OSXPhotosBackend,
    PhotosAuthorizationError,
    RESOURCE_TYPE_PAIRED_VIDEO,
    RESOURCE_TYPE_PHOTO,
    RESOURCE_TYPE_VIDEO,
)
from tools.icloud_photo_sync.runtime import run_apply, run_plan


@dataclass
class _FakePhoto:
    uuid: str
    original_filename: str
    date: datetime | None = None
    date_modified: datetime | None = None
    path: str | None = None
    path_live_photo: str | None = None
    ismissing: bool = False
    isphoto: bool = True
    ismovie: bool = False
    live_photo: bool = False
    intrash: bool = False
    shared: bool = False
    syndicated: bool = False
    saved_to_library: bool = True
    original_filesize: int | None = None
    uti_original: str | None = "public.heic"
    uti: str | None = "public.heic"
    burst: bool = False

    @property
    def filename(self) -> str:
        return self.original_filename


class _FakePhotosDB:
    def __init__(self, photos: list[_FakePhoto]) -> None:
        self._photos = list(photos)
        self._by_uuid = {photo.uuid: photo for photo in photos}

    def photos(self, *, images: bool = True, movies: bool = True, intrash: bool = False) -> list[_FakePhoto]:
        result: list[_FakePhoto] = []
        for photo in self._photos:
            if photo.intrash != intrash:
                continue
            if photo.isphoto and images:
                result.append(photo)
            elif photo.ismovie and movies:
                result.append(photo)
        return result

    def get_photo(self, uuid: str) -> _FakePhoto | None:
        return self._by_uuid.get(uuid)


def test_list_resources_maps_local_missing_live_and_video_and_filters_non_library(tmp_path: Path) -> None:
    local_photo = tmp_path / "originals" / "A" / "photo-1.heic"
    local_photo.parent.mkdir(parents=True)
    local_photo.write_bytes(b"local-heic-bytes")

    live_still = tmp_path / "originals" / "B" / "live-1.heic"
    live_still.parent.mkdir(parents=True)
    live_still.write_bytes(b"live-still-bytes")

    live_mov = tmp_path / "originals" / "B" / "live-1_3.mov"
    live_mov.write_bytes(b"live-mov-bytes")

    created = datetime(2025, 3, 15, 10, 30, 0, tzinfo=timezone.utc)
    fake_db = _FakePhotosDB(
        [
            _FakePhoto(
                uuid="uuid-1",
                original_filename="IMG_0001.HEIC",
                date=created,
                path=str(local_photo),
                original_filesize=999,
            ),
            _FakePhoto(
                uuid="uuid-2",
                original_filename="IMG_0002.HEIC",
                date=created,
                path=str(live_still),
                path_live_photo=str(live_mov),
                live_photo=True,
            ),
            _FakePhoto(
                uuid="uuid-3",
                original_filename="IMG_0003.HEIC",
                date=created,
                path=None,
                ismissing=True,
                original_filesize=4096,
            ),
            _FakePhoto(
                uuid="uuid-4",
                original_filename="VID_0004.MOV",
                date=created,
                path=None,
                ismissing=True,
                isphoto=False,
                ismovie=True,
                original_filesize=8192,
                uti_original="com.apple.quicktime-movie",
            ),
            _FakePhoto(uuid="uuid-trash", original_filename="TRASH.JPG", intrash=True),
            _FakePhoto(uuid="uuid-shared", original_filename="SHARED.JPG", shared=True),
            _FakePhoto(
                uuid="uuid-syndicated",
                original_filename="MSG.JPG",
                syndicated=True,
                saved_to_library=False,
            ),
        ]
    )

    backend = OSXPhotosBackend(library_path=tmp_path / "Photos.photoslibrary", db_factory=lambda **kw: fake_db)
    descriptors = backend.list_resources()

    assert [(d.asset_uuid, d.resource_index, d.resource_type, d.original_filename) for d in descriptors] == [
        ("uuid-1", 0, RESOURCE_TYPE_PHOTO, "IMG_0001.HEIC"),
        ("uuid-2", 0, RESOURCE_TYPE_PHOTO, "IMG_0002.HEIC"),
        ("uuid-2", 1, RESOURCE_TYPE_PAIRED_VIDEO, "IMG_0002.MOV"),
        ("uuid-3", 0, RESOURCE_TYPE_PHOTO, "IMG_0003.HEIC"),
        ("uuid-4", 0, RESOURCE_TYPE_VIDEO, "VID_0004.MOV"),
    ]

    by_key = {d.resource_key: d for d in descriptors}
    assert by_key["uuid-1:0:IMG_0001.HEIC"].local_path == str(local_photo)
    assert by_key["uuid-1:0:IMG_0001.HEIC"].file_size == len(b"local-heic-bytes")
    assert by_key["uuid-2:0:IMG_0002.HEIC"].media_subtypes == MEDIA_SUBTYPE_PHOTO_LIVE
    assert by_key["uuid-2:1:IMG_0002.MOV"].local_path == str(live_mov)
    assert by_key["uuid-2:1:IMG_0002.MOV"].file_size == len(b"live-mov-bytes")
    assert by_key["uuid-3:0:IMG_0003.HEIC"].local_path is None
    assert by_key["uuid-3:0:IMG_0003.HEIC"].file_size == 4096
    assert by_key["uuid-4:0:VID_0004.MOV"].media_type == MEDIA_TYPE_VIDEO
    assert by_key["uuid-1:0:IMG_0001.HEIC"].media_type == MEDIA_TYPE_IMAGE


@pytest.mark.parametrize(
    "exc",
    [
        PermissionError("Operation not permitted"),
        sqlite3.DatabaseError("authorization denied"),
        RuntimeError("Could not get authorizaton to use Photos: auth_status = 2"),
    ],
)
def test_authorization_errors_normalize_for_menu_bar_detection(tmp_path: Path, exc: Exception) -> None:
    def failing_db(**kwargs):
        raise exc

    backend = OSXPhotosBackend(library_path=tmp_path / "Photos.photoslibrary", db_factory=failing_db)
    with pytest.raises(PhotosAuthorizationError, match="photos authorization unavailable"):
        backend.list_resources()


def test_export_resource_uses_local_fast_path_and_osxphotos_exporter_for_missing(tmp_path: Path) -> None:
    local_photo = tmp_path / "local.heic"
    local_photo.write_bytes(b"local-original")

    fake_db = _FakePhotosDB(
        [
            _FakePhoto(uuid="local-1", original_filename="IMG_1.HEIC", path=str(local_photo)),
            _FakePhoto(uuid="cloud-1", original_filename="IMG_2.HEIC", path=None, ismissing=True),
            _FakePhoto(
                uuid="live-cloud",
                original_filename="IMG_3.HEIC",
                path=None,
                path_live_photo=None,
                ismissing=True,
                live_photo=True,
            ),
        ]
    )

    exporter_calls: list[dict] = []

    class FakeExporter:
        def __init__(self, photo: _FakePhoto) -> None:
            self.photo = photo

        def export(self, dest: str, **kwargs):
            exporter_calls.append({"uuid": self.photo.uuid, **kwargs})
            target = Path(dest) / self.photo.original_filename
            target.write_bytes(f"exported-{self.photo.uuid}".encode("utf-8"))
            return SimpleNamespace(exported=[str(target)], error=[])

    photokit_calls: list[tuple[str, bool, bool]] = []

    class FakeLiveAsset:
        live = True

        def __init__(self, uuid: str) -> None:
            self.uuid = uuid

        def export(self, dest: str, *, filename: str, version: int, overwrite: bool, photo: bool, video: bool):
            photokit_calls.append((self.uuid, photo, video))
            target = Path(dest) / filename
            target.write_bytes(b"icloud-live-mov")
            return [str(target)]

    class FakePhotoKitLib:
        def fetch_uuid(self, uuid: str):
            return FakeLiveAsset(uuid)

    backend = OSXPhotosBackend(
        library_path=tmp_path / "Photos.photoslibrary",
        db_factory=lambda **kw: fake_db,
        exporter_factory=FakeExporter,
        photokit_factory=FakePhotoKitLib,
    )

    out_local = backend.export_resource("local-1/L0/001", 0, tmp_path / "out" / "local.heic")
    assert out_local.read_bytes() == b"local-original"
    assert exporter_calls == []

    out_cloud = backend.export_resource("cloud-1/L0/001", 0, tmp_path / "out" / "cloud.heic")
    assert out_cloud.read_bytes() == b"exported-cloud-1"
    assert exporter_calls == [
        {
            "uuid": "cloud-1",
            "filename": "IMG_2.HEIC",
            "download_missing": True,
            "use_photokit": True,
            "live_photo": False,
            "overwrite": True,
            "increment": False,
        }
    ]

    out_live_mov = backend.export_resource("live-cloud/L0/001", 1, tmp_path / "out" / "live.mov")
    assert out_live_mov.read_bytes() == b"icloud-live-mov"
    assert photokit_calls == [("live-cloud", False, True)]


def test_export_resources_batch_isolates_item_errors_but_reraises_auth_errors(tmp_path: Path) -> None:
    fake_db = _FakePhotosDB(
        [
            _FakePhoto(uuid="cloud-ok", original_filename="OK.HEIC", ismissing=True),
            _FakePhoto(uuid="cloud-err", original_filename="ERR.HEIC", ismissing=True),
        ]
    )

    class MixedExporter:
        def __init__(self, photo: _FakePhoto) -> None:
            self.photo = photo

        def export(self, dest: str, **kwargs):
            if self.photo.uuid == "cloud-err":
                return SimpleNamespace(exported=[], error=[("ERR.HEIC", "network timeout")])
            target = Path(dest) / self.photo.original_filename
            target.write_bytes(b"ok-bytes")
            return SimpleNamespace(exported=[str(target)], error=[])

    backend = OSXPhotosBackend(
        library_path=tmp_path / "Photos.photoslibrary",
        db_factory=lambda **kw: fake_db,
        exporter_factory=MixedExporter,
    )
    results = backend.export_resources_batch(
        [
            {
                "request_id": "ok",
                "asset_local_identifier": "cloud-ok/L0/001",
                "resource_index": 0,
                "output_path": str(tmp_path / "ok.heic"),
            },
            {
                "request_id": "err",
                "asset_local_identifier": "cloud-err/L0/001",
                "resource_index": 0,
                "output_path": str(tmp_path / "err.heic"),
            },
        ]
    )
    assert results["ok"]["error"] is None
    assert Path(results["ok"]["output_path"]).read_bytes() == b"ok-bytes"
    assert results["err"]["output_path"] is None
    assert "network timeout" in results["err"]["error"]

    class AuthErrorExporter:
        def __init__(self, photo: _FakePhoto) -> None:
            self.photo = photo

        def export(self, dest: str, **kwargs):
            return SimpleNamespace(exported=[], error=[("OK.HEIC", "Could not get authorizaton to use Photos")])

    auth_backend = OSXPhotosBackend(
        library_path=tmp_path / "Photos.photoslibrary",
        db_factory=lambda **kw: fake_db,
        exporter_factory=AuthErrorExporter,
    )
    with pytest.raises(PhotosAuthorizationError, match="photos authorization unavailable"):
        auth_backend.export_resources_batch(
            [
                {
                    "request_id": "ok",
                    "asset_local_identifier": "cloud-ok/L0/001",
                    "resource_index": 0,
                    "output_path": str(tmp_path / "auth.heic"),
                }
            ]
        )


def test_run_plan_and_run_apply_end_to_end_with_osxphotos_backend(tmp_path: Path) -> None:
    local_photo = tmp_path / "Library.photoslibrary" / "originals" / "0" / "LOCAL.HEIC"
    local_photo.parent.mkdir(parents=True)
    local_photo.write_bytes(b"local-photo-payload")

    created = datetime(2025, 8, 20, 12, 0, 0, tzinfo=timezone.utc)
    fake_db = _FakePhotosDB(
        [
            _FakePhoto(uuid="asset-local", original_filename="IMG_1001.HEIC", date=created, path=str(local_photo)),
            _FakePhoto(uuid="asset-cloud", original_filename="IMG_1002.HEIC", date=created, path=None, ismissing=True),
        ]
    )

    class CloudExporter:
        def __init__(self, photo: _FakePhoto) -> None:
            self.photo = photo

        def export(self, dest: str, **kwargs):
            target = Path(dest) / self.photo.original_filename
            target.write_bytes(b"cloud-photo-payload")
            return SimpleNamespace(exported=[str(target)], error=[])

    backend = OSXPhotosBackend(
        library_path=tmp_path / "Library.photoslibrary",
        db_factory=lambda **kw: fake_db,
        exporter_factory=CloudExporter,
    )
    nas_root = tmp_path / "nas" / "Photos"
    nas_root.mkdir(parents=True)
    deleted_root = tmp_path / "nas" / "Deleted"
    logs_root = tmp_path / "logs"
    state_db = tmp_path / "state.sqlite3"
    stage_dir = tmp_path / "stage"

    plan_dir = run_plan(
        library_path=tmp_path / "Library.photoslibrary",
        nas_root=nas_root,
        logs_root=logs_root,
        state_db=state_db,
        stage_dir=stage_dir,
        plan_id="plan-osxphotos",
        photos_backend=backend,
    )

    summary = json.loads((plan_dir / "plan_summary.json").read_text(encoding="utf-8"))
    assert summary["asset_index_source"] == "osxphotos"
    assert summary["mirror_count"] == 2
    assert summary["unresolved_count"] == 0

    receipt_path = run_apply(
        plan_dir=plan_dir,
        nas_root=nas_root,
        deleted_root=deleted_root,
        state_db=state_db,
        photos_backend=backend,
    )
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["status"] == "success"
    assert receipt["mirrored"]["copied"] == 2
    assert (nas_root / "2025" / "08" / "IMG_1001.HEIC").read_bytes() == b"local-photo-payload"
    assert (nas_root / "2025" / "08" / "IMG_1002.HEIC").read_bytes() == b"cloud-photo-payload"


def test_real_osxphotos_api_contract_when_installed() -> None:
    osxphotos = pytest.importorskip("osxphotos")
    options = osxphotos.ExportOptions(
        download_missing=True,
        use_photokit=True,
        live_photo=True,
        overwrite=True,
        increment=False,
        location=False,
        persons=False,
        face_regions=False,
    )
    assert options.download_missing is True
    assert options.use_photokit is True
    assert hasattr(osxphotos, "PhotosDB")
    assert hasattr(osxphotos, "PhotoExporter")

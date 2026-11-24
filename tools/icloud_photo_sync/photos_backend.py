from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Callable


MEDIA_TYPE_IMAGE = 1
MEDIA_TYPE_VIDEO = 2
MEDIA_SUBTYPE_PHOTO_LIVE = 8

RESOURCE_TYPE_PHOTO = 1
RESOURCE_TYPE_VIDEO = 2
RESOURCE_TYPE_PAIRED_VIDEO = 9


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
    local_path: str | None = None

    @property
    def resource_key(self) -> str:
        return f"{self.asset_uuid}:{self.resource_index}:{self.original_filename}"


class PhotosAuthorizationError(RuntimeError):
    """Raised when macOS Photos / PhotoKit access is denied or unavailable."""


def _is_authorization_error(exc: BaseException) -> bool:
    if isinstance(exc, (PermissionError, PhotosAuthorizationError)):
        return True
    if type(exc).__name__ == "PhotoKitAuthError":
        return True
    message = str(exc).lower()
    markers = (
        "authorization denied",
        "authorization unavailable",
        "not authorized",
        "operation not permitted",
        "permission denied",
        "could not get authoriz",
    )
    return any(marker in message for marker in markers)


def _normalize_authorization_error(exc: BaseException) -> RuntimeError:
    if isinstance(exc, PhotosAuthorizationError):
        return exc
    if _is_authorization_error(exc):
        return PhotosAuthorizationError(f"photos authorization unavailable: {exc}")
    if isinstance(exc, RuntimeError):
        return exc
    return RuntimeError(str(exc))


def _iso_datetime(value: datetime | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if value.tzinfo is not None:
        return value.astimezone().isoformat()
    return value.isoformat()


def _existing_file(raw_path: str | Path | None) -> str | None:
    if not raw_path:
        return None
    candidate = Path(raw_path)
    try:
        if candidate.is_file():
            return str(candidate)
    except OSError:
        return None
    return None


def _resolve_file_size(local_path: str | None, reported_size: int | None) -> int | None:
    if local_path:
        try:
            return Path(local_path).stat().st_size
        except OSError:
            pass
    if isinstance(reported_size, int) and reported_size >= 0:
        return reported_size
    return None


def _live_video_filename(still_original_filename: str) -> str:
    stem = Path(still_original_filename).stem or still_original_filename
    return f"{stem}.MOV"


def _is_video_path(path: Path) -> bool:
    return path.suffix.lower() in {".mov", ".mp4", ".m4v"}


def _import_osxphotos():
    try:
        import osxphotos  # type: ignore[import-not-found]
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "osxphotos is not available in this Python runtime; "
            "install photo-steward dependencies or use the bundled Photo Steward App runtime"
        ) from exc
    return osxphotos


class OSXPhotosBackend:
    """Authoritative local macOS Photos library reader and iCloud original exporter via osxphotos."""

    def __init__(
        self,
        library_path: Path | None = None,
        db_path: Path | None = None,
        *,
        db_factory: Callable[..., Any] | None = None,
        exporter_factory: Callable[[Any], Any] | None = None,
        photokit_factory: Callable[[], Any] | None = None,
    ) -> None:
        self.library_path = Path(library_path) if library_path is not None else None
        self.db_path = Path(db_path) if db_path is not None else None
        self._db_factory = db_factory
        self._exporter_factory = exporter_factory
        self._photokit_factory = photokit_factory
        self._db: Any | None = None
        self._photokit_lib: Any | None = None

    def _open_db(self) -> Any:
        if self._db is not None:
            return self._db

        kwargs: dict[str, str] = {}
        if self.db_path is not None and self.db_path.exists():
            kwargs["dbfile"] = str(self.db_path)
            if self.library_path is not None:
                kwargs["library_path"] = str(self.library_path)
        elif self.library_path is not None:
            kwargs["dbfile"] = str(self.library_path)
        elif self.db_path is not None:
            kwargs["dbfile"] = str(self.db_path)

        try:
            if self._db_factory is not None:
                self._db = self._db_factory(**kwargs)
            else:
                osxphotos = _import_osxphotos()
                self._db = osxphotos.PhotosDB(**kwargs)
        except Exception as exc:  # noqa: BLE001
            raise _normalize_authorization_error(exc) from exc
        return self._db

    def _get_photokit_library(self) -> Any:
        if self._photokit_lib is not None:
            return self._photokit_lib
        try:
            if self._photokit_factory is not None:
                self._photokit_lib = self._photokit_factory()
            else:
                from osxphotos import photokit  # type: ignore[import-not-found]

                self._photokit_lib = photokit.PhotoLibrary()
        except Exception as exc:  # noqa: BLE001
            raise _normalize_authorization_error(exc) from exc
        return self._photokit_lib

    def list_resources(self) -> list[PhotosResourceDescriptor]:
        db = self._open_db()
        try:
            photos = db.photos(images=True, movies=True, intrash=False)
        except Exception as exc:  # noqa: BLE001
            raise _normalize_authorization_error(exc) from exc

        descriptors: list[PhotosResourceDescriptor] = []
        for photo in sorted(photos, key=lambda item: str(getattr(item, "uuid", ""))):
            if getattr(photo, "intrash", False):
                continue
            if getattr(photo, "shared", False):
                continue
            if getattr(photo, "syndicated", False) and not getattr(photo, "saved_to_library", True):
                continue

            asset_uuid = str(photo.uuid)
            asset_local_identifier = f"{asset_uuid}/L0/001"
            original_filename = getattr(photo, "original_filename", None) or getattr(photo, "filename", None) or f"{asset_uuid}.bin"
            creation_date = _iso_datetime(getattr(photo, "date", None))
            modification_date = _iso_datetime(getattr(photo, "date_modified", None))
            uti = getattr(photo, "uti_original", None) or getattr(photo, "uti", None)
            is_missing = bool(getattr(photo, "ismissing", False))
            local_primary = None if is_missing else _existing_file(getattr(photo, "path", None))
            primary_size = _resolve_file_size(local_primary, getattr(photo, "original_filesize", None))

            if getattr(photo, "ismovie", False):
                descriptors.append(
                    PhotosResourceDescriptor(
                        asset_local_identifier=asset_local_identifier,
                        asset_uuid=asset_uuid,
                        media_type=MEDIA_TYPE_VIDEO,
                        media_subtypes=0,
                        creation_date=creation_date,
                        modification_date=modification_date,
                        resource_index=0,
                        resource_type=RESOURCE_TYPE_VIDEO,
                        original_filename=original_filename,
                        uniform_type_identifier=uti,
                        file_size=primary_size,
                        local_path=local_primary,
                    )
                )
                continue

            is_live = bool(getattr(photo, "live_photo", False))
            descriptors.append(
                PhotosResourceDescriptor(
                    asset_local_identifier=asset_local_identifier,
                    asset_uuid=asset_uuid,
                    media_type=MEDIA_TYPE_IMAGE,
                    media_subtypes=MEDIA_SUBTYPE_PHOTO_LIVE if is_live else 0,
                    creation_date=creation_date,
                    modification_date=modification_date,
                    resource_index=0,
                    resource_type=RESOURCE_TYPE_PHOTO,
                    original_filename=original_filename,
                    uniform_type_identifier=uti,
                    file_size=primary_size,
                    local_path=local_primary,
                )
            )
            if is_live:
                local_live = _existing_file(getattr(photo, "path_live_photo", None))
                descriptors.append(
                    PhotosResourceDescriptor(
                        asset_local_identifier=asset_local_identifier,
                        asset_uuid=asset_uuid,
                        media_type=MEDIA_TYPE_IMAGE,
                        media_subtypes=MEDIA_SUBTYPE_PHOTO_LIVE,
                        creation_date=creation_date,
                        modification_date=modification_date,
                        resource_index=1,
                        resource_type=RESOURCE_TYPE_PAIRED_VIDEO,
                        original_filename=_live_video_filename(original_filename),
                        uniform_type_identifier="com.apple.quicktime-movie",
                        file_size=_resolve_file_size(local_live, None),
                        local_path=local_live,
                    )
                )

        return descriptors

    def _export_live_video_via_photokit(self, photo: Any, temp_dir: Path, filename: str) -> Path | None:
        photolib = self._get_photokit_library()
        asset_uuid = str(photo.uuid)
        asset = None
        try:
            asset = photolib.fetch_uuid(asset_uuid)
        except Exception as exc:  # noqa: BLE001
            if _is_authorization_error(exc):
                raise _normalize_authorization_error(exc) from exc
            burst_uuid = getattr(photo, "_info", {}).get("burstUUID") if getattr(photo, "burst", False) else None
            if burst_uuid and hasattr(photolib, "fetch_burst_uuid"):
                bursts = photolib.fetch_burst_uuid(burst_uuid, all=True)
                matches = [item for item in bursts if str(getattr(item, "uuid", "")).startswith(asset_uuid)]
                asset = matches[0] if matches else None
        if asset is None:
            return None

        if not getattr(asset, "live", False):
            return None

        version_original = 2
        if self._photokit_factory is None:
            from osxphotos import photokit  # type: ignore[import-not-found]

            version_original = photokit.PHOTOS_VERSION_ORIGINAL

        exported = asset.export(
            str(temp_dir),
            filename=filename,
            version=version_original,
            overwrite=True,
            photo=False,
            video=True,
        )
        for candidate in exported:
            path = Path(candidate)
            if path.is_file() and _is_video_path(path):
                return path
        return Path(exported[0]) if exported and Path(exported[0]).is_file() else None

    def _export_via_photo_exporter(self, photo: Any, resource_index: int, temp_dir: Path, filename: str) -> Path:
        want_live_video = resource_index == 1
        if self._exporter_factory is not None:
            exporter = self._exporter_factory(photo)
            results = exporter.export(
                str(temp_dir),
                filename=filename,
                download_missing=True,
                use_photokit=True,
                live_photo=want_live_video,
                overwrite=True,
                increment=False,
            )
        else:
            osxphotos = _import_osxphotos()
            options = osxphotos.ExportOptions(
                download_missing=True,
                use_photokit=True,
                live_photo=want_live_video,
                overwrite=True,
                increment=False,
                location=False,
                persons=False,
                face_regions=False,
            )
            exporter = osxphotos.PhotoExporter(photo)
            results = exporter.export(str(temp_dir), filename=filename, options=options)

        exported_paths = [Path(item) for item in getattr(results, "exported", []) if Path(item).is_file()]
        errors = list(getattr(results, "error", []) or [])

        if want_live_video:
            for candidate in exported_paths:
                if _is_video_path(candidate):
                    return candidate
        elif exported_paths:
            for candidate in exported_paths:
                if not _is_video_path(candidate) or getattr(photo, "ismovie", False):
                    return candidate
            return exported_paths[0]

        if errors:
            error_text = "; ".join(str(err[1] if isinstance(err, tuple) and len(err) > 1 else err) for err in errors)
            exc = RuntimeError(error_text)
            raise _normalize_authorization_error(exc)

        raise RuntimeError(f"osxphotos export produced no output for {photo.uuid}:{resource_index}")

    def export_resource(self, asset_local_identifier: str, resource_index: int, output_path: Path) -> Path:
        if resource_index not in (0, 1):
            raise RuntimeError(f"resource index out of range: {resource_index}")

        db = self._open_db()
        asset_uuid = asset_local_identifier.split("/", 1)[0]
        try:
            photo = db.get_photo(asset_uuid)
        except Exception as exc:  # noqa: BLE001
            raise _normalize_authorization_error(exc) from exc
        if photo is None:
            raise RuntimeError(f"asset not found: {asset_local_identifier}")

        if resource_index == 1 and not getattr(photo, "live_photo", False):
            raise RuntimeError(f"resource index out of range for non-live asset: {asset_local_identifier}")

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if resource_index == 0 and not getattr(photo, "ismissing", False):
            local_primary = _existing_file(getattr(photo, "path", None))
            if local_primary is not None:
                shutil.copy2(local_primary, output_path)
                return output_path
        elif resource_index == 1:
            local_live = _existing_file(getattr(photo, "path_live_photo", None))
            if local_live is not None:
                shutil.copy2(local_live, output_path)
                return output_path

        original_filename = getattr(photo, "original_filename", None) or getattr(photo, "filename", None) or output_path.name
        with TemporaryDirectory(prefix="osxphotos-export-", dir=output_path.parent) as temp_root:
            temp_dir = Path(temp_root)
            exported: Path | None = None
            try:
                if resource_index == 1:
                    exported = self._export_live_video_via_photokit(
                        photo,
                        temp_dir,
                        _live_video_filename(original_filename),
                    )
                if exported is None:
                    exported = self._export_via_photo_exporter(
                        photo,
                        resource_index,
                        temp_dir,
                        original_filename,
                    )
            except Exception as exc:  # noqa: BLE001
                raise _normalize_authorization_error(exc) from exc

            if not exported.is_file():
                raise RuntimeError(f"exported file missing: {exported}")
            output_path.unlink(missing_ok=True)
            shutil.move(str(exported), str(output_path))

        if not output_path.is_file():
            raise RuntimeError(f"exported file missing: {output_path}")
        return output_path

    def export_resources_batch(self, requests: list[dict]) -> dict[str, dict]:
        if not requests:
            return {}
        results: dict[str, dict] = {}
        for request in requests:
            request_id = request["request_id"]
            try:
                exported = self.export_resource(
                    asset_local_identifier=request["asset_local_identifier"],
                    resource_index=int(request["resource_index"]),
                    output_path=Path(request["output_path"]),
                )
                results[request_id] = {
                    "request_id": request_id,
                    "output_path": str(exported),
                    "error": None,
                }
            except PhotosAuthorizationError:
                raise
            except Exception as exc:  # noqa: BLE001
                results[request_id] = {
                    "request_id": request_id,
                    "output_path": None,
                    "error": str(exc),
                }
        return results

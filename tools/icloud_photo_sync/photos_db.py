from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path


APPLE_EPOCH = datetime(2001, 1, 1, tzinfo=timezone.utc)


@dataclass(frozen=True)
class AssetMeta:
    asset_uuid: str
    asset_local_identifier: str
    created_at: str
    original_filename: str
    local_primary_path: str | None
    stored_name: str
    directory: str


@dataclass(frozen=True)
class AssetIndexLoadResult:
    asset_index: dict[str, AssetMeta]
    source: str
    warning: str | None = None


def _apple_to_iso(raw_value: float | int | None) -> str | None:
    if raw_value is None:
        return None
    if not isinstance(raw_value, (int, float)):
        return None
    if raw_value <= 0:
        return None
    return (APPLE_EPOCH + timedelta(seconds=float(raw_value))).astimezone().isoformat()


def load_asset_index(library_path: Path, db_path: Path) -> dict[str, AssetMeta]:
    connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    cursor = connection.cursor()
    cursor.execute(
        """
        SELECT
            a.ZUUID,
            a.ZDIRECTORY,
            a.ZFILENAME,
            aa.ZORIGINALFILENAME,
            a.ZDATECREATED,
            a.ZADDEDDATE
        FROM ZASSET a
        LEFT JOIN ZADDITIONALASSETATTRIBUTES aa
            ON aa.ZASSET = a.Z_PK
        WHERE a.ZTRASHEDSTATE = 0
          AND a.ZDIRECTORY IS NOT NULL
          AND a.ZFILENAME IS NOT NULL
        ORDER BY a.ZDATECREATED, a.ZADDEDDATE, a.Z_PK
        """
    )

    asset_index: dict[str, AssetMeta] = {}
    for asset_uuid, directory, stored_name, original_name, created_raw, added_raw in cursor:
        created_at = _apple_to_iso(created_raw) or _apple_to_iso(added_raw) or datetime.now(timezone.utc).isoformat()
        local_path = library_path / "originals" / directory / stored_name
        asset_index[asset_uuid] = AssetMeta(
            asset_uuid=asset_uuid,
            asset_local_identifier=f"{asset_uuid}/L0/001",
            created_at=created_at,
            original_filename=original_name or stored_name,
            local_primary_path=str(local_path) if local_path.exists() else None,
            stored_name=stored_name,
            directory=directory,
        )
    connection.close()
    return asset_index


def load_asset_index_if_available(library_path: Path, db_path: Path) -> AssetIndexLoadResult:
    try:
        asset_index = load_asset_index(library_path=library_path, db_path=db_path)
    except (sqlite3.Error, OSError) as exc:
        return AssetIndexLoadResult(
            asset_index={},
            source="photos_bridge_only",
            warning=f"{type(exc).__name__}: {exc}",
        )
    return AssetIndexLoadResult(asset_index=asset_index, source="photos_db")

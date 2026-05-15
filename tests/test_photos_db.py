import sqlite3
from pathlib import Path

from tools.icloud_photo_sync.photos_db import load_asset_index_if_available


def test_load_asset_index_if_available_returns_bridge_only_status_when_db_denied(
    monkeypatch, tmp_path: Path
) -> None:
    library_path = tmp_path / "Library.photoslibrary"
    db_path = library_path / "database" / "Photos.sqlite"

    def fake_connect(*args, **kwargs):
        raise sqlite3.DatabaseError("authorization denied")

    monkeypatch.setattr(sqlite3, "connect", fake_connect)

    result = load_asset_index_if_available(library_path=library_path, db_path=db_path)

    assert result.source == "photos_bridge_only"
    assert result.asset_index == {}
    assert "authorization denied" in (result.warning or "")


from pathlib import Path

from tools.icloud_photo_sync.fingerprint import FingerprintService
from tools.icloud_photo_sync.state import StateStore


def test_fingerprint_service_reuses_unchanged_file_hash(tmp_path: Path) -> None:
    db_path = tmp_path / "state.sqlite3"
    source = tmp_path / "sample.txt"
    source.write_text("hello", encoding="utf-8")

    calls = {"count": 0}

    def fake_hasher(path: Path) -> str:
        assert path == source
        calls["count"] += 1
        return "hash-1"

    store = StateStore(db_path)
    service = FingerprintService(store=store, hasher=fake_hasher)

    first = service.fingerprint_path("nas", "sample", source)
    second = service.fingerprint_path("nas", "sample", source)

    assert first.sha256 == "hash-1"
    assert second.sha256 == "hash-1"
    assert calls["count"] == 1

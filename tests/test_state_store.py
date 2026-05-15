from pathlib import Path

from tools.icloud_photo_sync.state import StateStore


def test_state_store_caches_fingerprints_and_bindings(tmp_path: Path) -> None:
    db_path = tmp_path / "state.sqlite3"
    store = StateStore(db_path)

    store.upsert_cached_fingerprint(
        source_kind="nas",
        resource_key="2024/10/IMG_0001.JPG",
        state_token="123:456:789",
        sha256="abc",
        bytes_count=123,
    )
    store.upsert_binding(
        resource_key="asset-1:0:IMG_0001.JPG",
        relative_path="2024/10/IMG_0001.JPG",
        plan_id="plan-1",
    )
    store.record_plan(
        plan_id="plan-1",
        plan_dir="/tmp/plan-1",
        summary_json='{"mirror_count": 1}',
    )

    cached = store.get_cached_fingerprint("nas", "2024/10/IMG_0001.JPG", "123:456:789")
    assert cached is not None
    assert cached.sha256 == "abc"
    assert cached.bytes_count == 123

    assert store.get_binding("asset-1:0:IMG_0001.JPG") == "2024/10/IMG_0001.JPG"
    assert store.plan_exists("plan-1") is True


def test_state_store_cache_miss_on_changed_state_token(tmp_path: Path) -> None:
    db_path = tmp_path / "state.sqlite3"
    store = StateStore(db_path)
    store.upsert_cached_fingerprint(
        source_kind="icloud",
        resource_key="asset-1:0:IMG_0001.JPG",
        state_token="old-token",
        sha256="abc",
        bytes_count=123,
    )

    assert store.get_cached_fingerprint("icloud", "asset-1:0:IMG_0001.JPG", "new-token") is None


def test_state_store_caches_json_metadata_by_scope_and_state_token(tmp_path: Path) -> None:
    db_path = tmp_path / "state.sqlite3"
    store = StateStore(db_path)

    store.upsert_cached_metadata(
        cache_scope="google_review_review_capture_time",
        resource_key="/tmp/a.jpg",
        state_token="size:mtime:ctime",
        payload={"capture_time": "2013:01:02 03:04:05", "status": "ok"},
    )

    cached = store.get_cached_metadata(
        cache_scope="google_review_review_capture_time",
        resource_key="/tmp/a.jpg",
        state_token="size:mtime:ctime",
    )

    assert cached is not None
    assert cached.payload["capture_time"] == "2013:01:02 03:04:05"
    assert (
        store.get_cached_metadata(
            cache_scope="google_review_review_capture_time",
            resource_key="/tmp/a.jpg",
            state_token="changed-token",
        )
        is None
    )

import json
from pathlib import Path

from tools.icloud_photo_sync.google_review import (
    apply_google_review_rebucket,
    plan_google_review_rebucket,
)


def _write_bytes(path: Path, content: bytes = b"x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_plan_google_review_rebucket_splits_exact_capture_time_matches(tmp_path: Path) -> None:
    review_root = tmp_path / "GoogleDrive_GooglePhotosReview_2026-04-10"
    nas_root = tmp_path / "Photos"
    logs_root = tmp_path / "logs"
    state_db = tmp_path / "state.sqlite3"

    biom = review_root / "00_EventArchive" / "2018" / "181208_CityU_BioM_0001.jpg"
    event = review_root / "00_EventArchive" / "2017" / "event.jpg"
    alpha = review_root / "01_UnmatchedReview" / "2013" / "alpha.jpg"
    root = review_root / "01_UnmatchedReview" / "_RootLoose" / "root.jpg"
    nas_alpha = nas_root / "2013" / "01" / "nas_alpha.jpg"
    nas_event = nas_root / "2017" / "12" / "nas_event.jpg"

    for path in (biom, event, alpha, root, nas_alpha, nas_event):
        _write_bytes(path)

    metadata = {
        str(biom): {"capture_time": "2018:12:08 09:00:00", "status": "ok"},
        str(event): {"capture_time": "2017:12:30 10:20:30", "status": "ok"},
        str(alpha): {"capture_time": "2013:01:02 03:04:05", "status": "ok"},
        str(root): {"capture_time": "2014:05:06 07:08:09", "status": "ok"},
        str(nas_alpha): {"capture_time": "2013:01:02 03:04:05", "status": "ok"},
        str(nas_event): {"capture_time": "2017:12:30 10:20:30", "status": "ok"},
    }

    plan_dir = plan_google_review_rebucket(
        review_root=review_root,
        nas_root=nas_root,
        logs_root=logs_root,
        state_db=state_db,
        plan_id="google-review-plan-1",
        metadata_resolver=lambda path: metadata[str(path)],
    )

    summary = _read_json(plan_dir / "plan_summary.json")
    move_items = _read_json(plan_dir / "rebucket_moves.json")["items"]

    assert summary["plan_id"] == "google-review-plan-1"
    assert summary["event_archive_keep_count"] == 1
    assert summary["event_archive_rebucket_count"] == 1
    assert summary["exact_match_count"] == 2
    assert summary["no_exact_match_count"] == 1
    assert summary["planned_move_count"] == 3

    move_map = {item["source_relative_path"]: item for item in move_items}
    assert (
        move_map["00_EventArchive/2017/event.jpg"]["target_relative_path"]
        == "01_UnmatchedReview/01_ExactCaptureTimeMatch/2017/event.jpg"
    )
    assert move_map["00_EventArchive/2017/event.jpg"]["matched_nas_paths"] == ["2017/12/nas_event.jpg"]
    assert (
        move_map["01_UnmatchedReview/2013/alpha.jpg"]["target_relative_path"]
        == "01_UnmatchedReview/01_ExactCaptureTimeMatch/2013/alpha.jpg"
    )
    assert move_map["01_UnmatchedReview/2013/alpha.jpg"]["matched_nas_paths"] == ["2013/01/nas_alpha.jpg"]
    assert (
        move_map["01_UnmatchedReview/_RootLoose/root.jpg"]["target_relative_path"]
        == "01_UnmatchedReview/02_NoExactCaptureTimeMatch/2014/root.jpg"
    )
    assert move_map["01_UnmatchedReview/_RootLoose/root.jpg"]["reason"] == "nas_no_exact_capture_time_match"


def test_plan_google_review_rebucket_reuses_cached_capture_metadata(tmp_path: Path) -> None:
    review_root = tmp_path / "GoogleDrive_GooglePhotosReview_2026-04-10"
    nas_root = tmp_path / "Photos"
    logs_root = tmp_path / "logs"
    state_db = tmp_path / "state.sqlite3"

    review_file = review_root / "01_UnmatchedReview" / "2013" / "alpha.jpg"
    nas_file = nas_root / "2013" / "01" / "nas_alpha.jpg"
    for path in (review_file, nas_file):
        _write_bytes(path)

    calls: list[str] = []
    metadata = {
        str(review_file): {"capture_time": "2013:01:02 03:04:05", "status": "ok"},
        str(nas_file): {"capture_time": "2013:01:02 03:04:05", "status": "ok"},
    }

    def resolver(path: Path) -> dict:
        calls.append(str(path))
        return metadata[str(path)]

    plan_google_review_rebucket(
        review_root=review_root,
        nas_root=nas_root,
        logs_root=logs_root,
        state_db=state_db,
        plan_id="google-review-plan-cache-1",
        metadata_resolver=resolver,
    )
    first_call_count = len(calls)

    plan_google_review_rebucket(
        review_root=review_root,
        nas_root=nas_root,
        logs_root=logs_root,
        state_db=state_db,
        plan_id="google-review-plan-cache-2",
        metadata_resolver=resolver,
    )
    second_call_count = len(calls) - first_call_count

    assert first_call_count == 2
    assert second_call_count == 0


def test_apply_google_review_rebucket_moves_files_and_prunes_dirs(tmp_path: Path) -> None:
    review_root = tmp_path / "GoogleDrive_GooglePhotosReview_2026-04-10"
    nas_root = tmp_path / "Photos"
    logs_root = tmp_path / "logs"
    state_db = tmp_path / "state.sqlite3"

    biom = review_root / "00_EventArchive" / "2018" / "181208_CityU_BioM_0001.jpg"
    event = review_root / "00_EventArchive" / "2017" / "event.jpg"
    alpha = review_root / "01_UnmatchedReview" / "2013" / "alpha.jpg"
    root = review_root / "01_UnmatchedReview" / "_RootLoose" / "root.jpg"
    nas_alpha = nas_root / "2013" / "01" / "nas_alpha.jpg"
    nas_event = nas_root / "2017" / "12" / "nas_event.jpg"

    for path in (biom, event, alpha, root, nas_alpha, nas_event):
        _write_bytes(path)

    metadata = {
        str(biom): {"capture_time": "2018:12:08 09:00:00", "status": "ok"},
        str(event): {"capture_time": "2017:12:30 10:20:30", "status": "ok"},
        str(alpha): {"capture_time": "2013:01:02 03:04:05", "status": "ok"},
        str(root): {"capture_time": "2014:05:06 07:08:09", "status": "ok"},
        str(nas_alpha): {"capture_time": "2013:01:02 03:04:05", "status": "ok"},
        str(nas_event): {"capture_time": "2017:12:30 10:20:30", "status": "ok"},
    }

    plan_dir = plan_google_review_rebucket(
        review_root=review_root,
        nas_root=nas_root,
        logs_root=logs_root,
        state_db=state_db,
        plan_id="google-review-plan-apply",
        metadata_resolver=lambda path: metadata[str(path)],
    )

    receipt_path = apply_google_review_rebucket(plan_dir)
    receipt = _read_json(receipt_path)

    assert receipt["plan_id"] == "google-review-plan-apply"
    assert receipt["moved_count"] == 3
    assert receipt["pruned_empty_directories"] >= 2

    assert biom.exists()
    assert not event.exists()
    assert not alpha.exists()
    assert not root.exists()
    assert (
        review_root / "01_UnmatchedReview" / "01_ExactCaptureTimeMatch" / "2017" / "event.jpg"
    ).exists()
    assert (
        review_root / "01_UnmatchedReview" / "01_ExactCaptureTimeMatch" / "2013" / "alpha.jpg"
    ).exists()
    assert (
        review_root / "01_UnmatchedReview" / "02_NoExactCaptureTimeMatch" / "2014" / "root.jpg"
    ).exists()
    assert not (review_root / "00_EventArchive" / "2017").exists()
    assert not (review_root / "01_UnmatchedReview" / "_RootLoose").exists()
    assert list((review_root / "01_UnmatchedReview").glob("rebucket_summary_*.json"))

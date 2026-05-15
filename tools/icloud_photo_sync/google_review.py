from __future__ import annotations

import json
import os
import plistlib
import shutil
import subprocess
import uuid
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Callable

from .state import StateStore
from .utils import file_state_token


EXACT_BUCKET = "01_ExactCaptureTimeMatch"
NO_MATCH_BUCKET = "02_NoExactCaptureTimeMatch"
KEEP_EVENT_YEAR = "2018"
KEEP_EVENT_PREFIX = "181208_CityU_BioM"
UNKNOWN_YEAR = "_UnknownYear"
IMAGE_SUFFIXES = {
    ".arw",
    ".bmp",
    ".cr2",
    ".dng",
    ".gif",
    ".heic",
    ".heif",
    ".jpeg",
    ".jpg",
    ".nef",
    ".png",
    ".tif",
    ".tiff",
    ".webp",
}
VIDEO_SUFFIXES = {
    ".avi",
    ".m4v",
    ".mov",
    ".mp4",
}
MEDIA_SUFFIXES = IMAGE_SUFFIXES | VIDEO_SUFFIXES


def _json_dumps(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_json_dumps(payload), encoding="utf-8")


def _write_jsonl(path: Path, items: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in items)
    path.write_text(text, encoding="utf-8")


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def _now() -> datetime:
    return datetime.now().astimezone()


def _media_kind(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in IMAGE_SUFFIXES:
        return "image"
    if suffix in VIDEO_SUFFIXES:
        return "video"
    return "other"


def _is_media_file(path: Path) -> bool:
    return path.suffix.lower() in MEDIA_SUFFIXES


def extract_capture_metadata_via_sips(path: Path) -> dict:
    media_kind = _media_kind(path)
    if media_kind != "image":
        return {
            "capture_time": None,
            "status": "not_supported_type",
            "media_kind": media_kind,
            "type_identifier": None,
        }

    result = subprocess.run(
        ["sips", "-g", "allxml", str(path)],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return {
            "capture_time": None,
            "status": "extract_error",
            "media_kind": media_kind,
            "type_identifier": None,
            "stderr": result.stderr.decode("utf-8", errors="replace").strip(),
        }

    try:
        payload = plistlib.loads(result.stdout)
    except Exception as exc:  # noqa: BLE001
        return {
            "capture_time": None,
            "status": "parse_error",
            "media_kind": media_kind,
            "type_identifier": None,
            "error": str(exc),
        }

    capture_time = payload.get("creation")
    return {
        "capture_time": capture_time if isinstance(capture_time, str) and capture_time else None,
        "status": "ok" if capture_time else "missing_creation",
        "media_kind": media_kind,
        "type_identifier": payload.get("typeIdentifier"),
    }


def _resolve_cached_metadata(
    *,
    store: StateStore,
    cache_scope: str,
    path: Path,
    metadata_resolver: Callable[[Path], dict],
) -> dict:
    state_token = file_state_token(path)
    resource_key = str(path)
    cached = store.get_cached_metadata(cache_scope, resource_key, state_token)
    if cached is not None:
        return cached.payload

    payload = dict(metadata_resolver(path))
    payload.setdefault("capture_time", None)
    payload.setdefault("status", "missing_creation")
    payload.setdefault("media_kind", _media_kind(path))
    store.upsert_cached_metadata(
        cache_scope=cache_scope,
        resource_key=resource_key,
        state_token=state_token,
        payload=payload,
    )
    return payload


def _year_hint_from_relative_path(relative_path: str) -> str | None:
    parts = Path(relative_path).parts
    if not parts:
        return None

    if parts[0] == "00_EventArchive" and len(parts) >= 2 and parts[1].isdigit() and len(parts[1]) == 4:
        return parts[1]

    if parts[0] != "01_UnmatchedReview":
        return None

    if len(parts) >= 2 and parts[1].isdigit() and len(parts[1]) == 4:
        return parts[1]

    if len(parts) >= 3 and parts[1] in {EXACT_BUCKET, NO_MATCH_BUCKET} and parts[2].isdigit() and len(parts[2]) == 4:
        return parts[2]

    return None


def _capture_year(capture_time: str | None) -> str | None:
    if not capture_time or len(capture_time) < 4:
        return None
    year = capture_time[:4]
    return year if year.isdigit() else None


def _collect_review_sources(review_root: Path) -> tuple[list[dict], int, int]:
    items: list[dict] = []
    event_keep_count = 0
    event_rebucket_count = 0

    for path in sorted(review_root.rglob("*")):
        if not path.is_file() or not _is_media_file(path):
            continue
        relative_path = path.relative_to(review_root).as_posix()
        parts = Path(relative_path).parts
        if not parts:
            continue
        if parts[0] == "00_EventArchive":
            if len(parts) >= 3 and parts[1] == KEEP_EVENT_YEAR and path.name.startswith(KEEP_EVENT_PREFIX):
                event_keep_count += 1
                continue
            event_rebucket_count += 1
        elif parts[0] != "01_UnmatchedReview":
            continue

        items.append(
            {
                "source_relative_path": relative_path,
                "source_absolute_path": str(path),
                "source_name": path.name,
                "year_hint": _year_hint_from_relative_path(relative_path),
                "media_kind": _media_kind(path),
            }
        )

    return items, event_keep_count, event_rebucket_count


def _collect_nas_index(
    *,
    store: StateStore,
    nas_root: Path,
    relevant_years: set[str],
    metadata_resolver: Callable[[Path], dict],
) -> tuple[dict[str, list[str]], dict]:
    capture_index: dict[str, list[str]] = defaultdict(list)
    scanned_files = 0
    indexed_files = 0

    for year in sorted(relevant_years):
        year_root = nas_root / year
        if not year_root.exists():
            continue
        for path in sorted(year_root.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in IMAGE_SUFFIXES:
                continue
            scanned_files += 1
            payload = _resolve_cached_metadata(
                store=store,
                cache_scope="google_review_nas_capture_time",
                path=path,
                metadata_resolver=metadata_resolver,
            )
            capture_time = payload.get("capture_time")
            if not isinstance(capture_time, str) or not capture_time:
                continue
            indexed_files += 1
            capture_index[capture_time].append(path.relative_to(nas_root).as_posix())

    for paths in capture_index.values():
        paths.sort()

    return capture_index, {
        "scanned_files": scanned_files,
        "indexed_files": indexed_files,
        "capture_time_key_count": len(capture_index),
        "scanned_years": sorted(relevant_years),
    }


def _assign_unique_targets(items: list[dict]) -> None:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for item in items:
        grouped[item["target_relative_path"]].append(item)

    for desired_target, group in grouped.items():
        if len(group) == 1:
            group[0]["resolved_target_relative_path"] = desired_target
            continue

        preferred: dict | None = None
        for item in group:
            if item["source_relative_path"] == desired_target:
                preferred = item
                break
        if preferred is None:
            preferred = sorted(group, key=lambda item: item["source_relative_path"])[0]
        preferred["resolved_target_relative_path"] = desired_target

        duplicate_index = 1
        for item in sorted(group, key=lambda current: current["source_relative_path"]):
            if item is preferred:
                continue
            target_path = Path(desired_target)
            resolved_name = f"{target_path.stem}__bucketdup{duplicate_index}{target_path.suffix}"
            item["resolved_target_relative_path"] = (
                target_path.parent / resolved_name
            ).as_posix()
            duplicate_index += 1


def plan_google_review_rebucket(
    *,
    review_root: Path,
    nas_root: Path,
    logs_root: Path,
    state_db: Path,
    plan_id: str | None = None,
    metadata_resolver: Callable[[Path], dict] | None = None,
) -> Path:
    review_root = Path(review_root)
    nas_root = Path(nas_root)
    logs_root = Path(logs_root)
    state_db = Path(state_db)
    metadata_resolver = metadata_resolver or extract_capture_metadata_via_sips

    now = _now()
    plan_id = plan_id or now.strftime("google-review-%Y%m%dT%H%M%S")
    plan_dir = logs_root / now.strftime("%Y-%m-%d") / plan_id
    plan_dir.mkdir(parents=True, exist_ok=True)

    store = StateStore(state_db)
    try:
        sources, event_keep_count, event_rebucket_count = _collect_review_sources(review_root)
        review_manifest: list[dict] = []
        relevant_years: set[str] = set()

        for source in sources:
            source_path = Path(source["source_absolute_path"])
            payload = _resolve_cached_metadata(
                store=store,
                cache_scope="google_review_review_capture_time",
                path=source_path,
                metadata_resolver=metadata_resolver,
            )
            capture_time = payload.get("capture_time")
            year = _capture_year(capture_time)
            if year is not None:
                relevant_years.add(year)

            review_manifest.append(
                {
                    **source,
                    "capture_time": capture_time,
                    "capture_status": payload.get("status"),
                    "type_identifier": payload.get("type_identifier"),
                }
            )

        nas_index, nas_summary = _collect_nas_index(
            store=store,
            nas_root=nas_root,
            relevant_years=relevant_years,
            metadata_resolver=metadata_resolver,
        )
    finally:
        store.close()

    exact_match_count = 0
    no_exact_match_count = 0

    for item in review_manifest:
        capture_time = item.get("capture_time")
        capture_year = _capture_year(capture_time)
        bucket_year = capture_year or item.get("year_hint") or UNKNOWN_YEAR
        matched_nas_paths = nas_index.get(capture_time, []) if capture_time else []
        if matched_nas_paths:
            exact_match_count += 1
            bucket_name = EXACT_BUCKET
            reason = "nas_exact_capture_time_match"
        else:
            no_exact_match_count += 1
            bucket_name = NO_MATCH_BUCKET
            reason = "review_capture_time_missing" if not capture_time else "nas_no_exact_capture_time_match"

        item["bucket_name"] = bucket_name
        item["bucket_year"] = bucket_year
        item["reason"] = reason
        item["matched_nas_paths"] = matched_nas_paths
        item["target_relative_path"] = (
            Path("01_UnmatchedReview") / bucket_name / bucket_year / item["source_name"]
        ).as_posix()

    _assign_unique_targets(review_manifest)
    move_items = [
        {
            **item,
            "target_relative_path": item["resolved_target_relative_path"],
        }
        for item in review_manifest
        if item["source_relative_path"] != item["resolved_target_relative_path"]
    ]

    summary = {
        "plan_id": plan_id,
        "review_root": str(review_root),
        "nas_root": str(nas_root),
        "state_db": str(state_db),
        "review_file_count": len(review_manifest),
        "event_archive_keep_count": event_keep_count,
        "event_archive_rebucket_count": event_rebucket_count,
        "exact_match_count": exact_match_count,
        "no_exact_match_count": no_exact_match_count,
        "planned_move_count": len(move_items),
        "unchanged_count": len(review_manifest) - len(move_items),
        "nas_index": nas_summary,
    }

    _write_json(plan_dir / "plan_summary.json", summary)
    _write_json(plan_dir / "rebucket_moves.json", {"plan_id": plan_id, "items": move_items})
    _write_jsonl(plan_dir / "review_manifest.jsonl", review_manifest)
    return plan_dir


def _prune_empty_dirs(root: Path) -> int:
    removed = 0
    if not root.exists():
        return removed
    for current_root, _dirnames, _filenames in os.walk(root, topdown=False):
        current_path = Path(current_root)
        if current_path == root:
            continue
        try:
            next(current_path.iterdir())
            continue
        except StopIteration:
            current_path.rmdir()
            removed += 1
    return removed


def apply_google_review_rebucket(plan_dir: Path) -> Path:
    plan_dir = Path(plan_dir)
    summary = _read_json(plan_dir / "plan_summary.json")
    move_items = _read_json(plan_dir / "rebucket_moves.json")["items"]
    review_manifest = _read_jsonl(plan_dir / "review_manifest.jsonl")

    review_root = Path(summary["review_root"])
    plan_id = summary["plan_id"]
    staging_root = review_root / ".rebucket-staging" / plan_id
    staging_root.mkdir(parents=True, exist_ok=True)

    staged_items: list[tuple[Path, Path]] = []
    moved_count = 0
    try:
        for index, item in enumerate(move_items):
            source_path = review_root / item["source_relative_path"]
            if not source_path.exists():
                raise FileNotFoundError(f"待移动源文件不存在: {source_path}")
            staged_path = staging_root / f"{index:06d}-{uuid.uuid4().hex}{source_path.suffix}"
            staged_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source_path), str(staged_path))
            staged_items.append((staged_path, review_root / item["target_relative_path"]))

        for staged_path, target_path in staged_items:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            if target_path.exists():
                raise FileExistsError(f"目标路径已存在: {target_path}")
            shutil.move(str(staged_path), str(target_path))
            moved_count += 1
    finally:
        if staging_root.exists():
            shutil.rmtree(staging_root, ignore_errors=True)

    pruned_empty_directories = 0
    pruned_empty_directories += _prune_empty_dirs(review_root / "00_EventArchive")
    pruned_empty_directories += _prune_empty_dirs(review_root / "01_UnmatchedReview")

    date_stamp = _now().strftime("%Y-%m-%d")
    unmatched_root = review_root / "01_UnmatchedReview"
    _write_json(
        unmatched_root / f"rebucket_summary_{date_stamp}.json",
        {
            **summary,
            "moved_count": moved_count,
            "pruned_empty_directories": pruned_empty_directories,
            "applied_at": _now().isoformat(),
        },
    )
    _write_jsonl(unmatched_root / f"rebucket_manifest_{date_stamp}.jsonl", review_manifest)
    _write_json(
        unmatched_root / EXACT_BUCKET / f"manifest_{date_stamp}.json",
        {
            "plan_id": plan_id,
            "items": [item for item in review_manifest if item["bucket_name"] == EXACT_BUCKET],
        },
    )
    _write_json(
        unmatched_root / NO_MATCH_BUCKET / f"manifest_{date_stamp}.json",
        {
            "plan_id": plan_id,
            "items": [item for item in review_manifest if item["bucket_name"] == NO_MATCH_BUCKET],
        },
    )

    receipt_path = plan_dir / "apply_receipt.json"
    _write_json(
        receipt_path,
        {
            "plan_id": plan_id,
            "review_root": str(review_root),
            "moved_count": moved_count,
            "pruned_empty_directories": pruned_empty_directories,
            "receipt_written_at": _now().isoformat(),
        },
    )
    return receipt_path

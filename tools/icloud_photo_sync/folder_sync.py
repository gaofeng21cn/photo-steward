from __future__ import annotations

import hashlib
import json
import os
import shutil
import unicodedata
import uuid
from datetime import datetime
from pathlib import Path


IGNORED_NAMES = {".DS_Store"}


def normalize_relative_path(relative_path: str) -> str:
    return unicodedata.normalize("NFC", relative_path.replace(os.sep, "/"))


def _json_dumps(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_json_dumps(payload), encoding="utf-8")


def _write_jsonl(path: Path, items: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in items)
    path.write_text(text, encoding="utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _ancestors(normalized_relative_path: str) -> list[str]:
    parts = normalized_relative_path.split("/")
    return ["/".join(parts[:index]) for index in range(1, len(parts))]


def _collect_tree(root: Path) -> tuple[dict[str, dict], set[str], list[dict]]:
    files: dict[str, dict] = {}
    directories: set[str] = set()
    unresolved: list[dict] = []

    for path in sorted(root.rglob("*")):
        relative_path = path.relative_to(root).as_posix()
        if path.name in IGNORED_NAMES:
            continue

        normalized_path = normalize_relative_path(relative_path)
        if path.is_symlink():
            link_target = os.readlink(path)
            entry = {
                "relative_path": relative_path,
                "normalized_relative_path": normalized_path,
                "absolute_path": str(path),
                "size": len(link_target.encode("utf-8")),
                "sha256": None,
                "link_target": link_target,
                "signature": f"symlink:{link_target}",
                "entry_type": "symlink",
            }
            if normalized_path in files:
                unresolved.append(
                    {
                        "path": relative_path,
                        "reason": "duplicate_normalized_path",
                        "existing_path": files[normalized_path]["relative_path"],
                    }
                )
                continue
            files[normalized_path] = entry
            continue

        if path.is_dir():
            directories.add(normalized_path)
            continue

        if not path.is_file():
            unresolved.append(
                {
                    "path": relative_path,
                    "reason": "unsupported_entry_type",
                }
            )
            continue

        file_sha256 = _sha256(path)
        entry = {
            "relative_path": relative_path,
            "normalized_relative_path": normalized_path,
            "absolute_path": str(path),
            "size": path.stat().st_size,
            "sha256": file_sha256,
            "link_target": None,
            "signature": file_sha256,
            "entry_type": "file",
        }
        if normalized_path in files:
            unresolved.append(
                {
                    "path": relative_path,
                    "reason": "duplicate_normalized_path",
                    "existing_path": files[normalized_path]["relative_path"],
                }
            )
            continue
        files[normalized_path] = entry

    return files, directories, unresolved


def plan_folder_sync(
    *,
    source_root: Path,
    target_root: Path,
    review_root: Path,
    logs_root: Path,
    plan_id: str | None = None,
) -> Path:
    source_root = Path(source_root)
    target_root = Path(target_root)
    review_root = Path(review_root)
    logs_root = Path(logs_root)

    plan_id = plan_id or datetime.now().astimezone().strftime("folder-plan-%Y%m%dT%H%M%S")
    dated_dir = logs_root / datetime.now().astimezone().strftime("%Y-%m-%d") / plan_id
    dated_dir.mkdir(parents=True, exist_ok=True)

    source_files, source_dirs, source_unresolved = _collect_tree(source_root)
    target_files, _target_dirs, target_unresolved = _collect_tree(target_root)
    unresolved = [
        *({"side": "source", **item} for item in source_unresolved),
        *({"side": "target", **item} for item in target_unresolved),
    ]

    source_hash_index: dict[str, list[str]] = {}
    for entry in source_files.values():
        source_hash_index.setdefault(entry["signature"], []).append(entry["relative_path"])
    for paths in source_hash_index.values():
        paths.sort()

    move_items: list[dict] = []
    kept_target_paths: set[str] = set()

    for normalized_path, target_entry in sorted(target_files.items()):
        source_entry = source_files.get(normalized_path)
        if source_entry and source_entry["signature"] == target_entry["signature"]:
            kept_target_paths.add(normalized_path)
            continue

        duplicate_source_paths: list[str] = []
        if source_entry:
            reason = "replace_conflict"
        elif normalized_path in source_dirs:
            reason = "path_type_conflict_source_directory"
        elif any(ancestor in source_files for ancestor in _ancestors(normalized_path)):
            reason = "path_blocked_by_source_file"
        elif target_entry["signature"] in source_hash_index:
            reason = "target_only_duplicate_of_source"
            duplicate_source_paths = source_hash_index[target_entry["signature"]]
        else:
            reason = "target_only_missing_in_source"

        move_items.append(
            {
                "target_relative_path": target_entry["relative_path"],
                "target_normalized_relative_path": normalized_path,
                "review_relative_path": target_entry["relative_path"],
                "reason": reason,
                "duplicate_source_paths": duplicate_source_paths,
                "sha256": target_entry["sha256"],
                "link_target": target_entry["link_target"],
                "entry_type": target_entry["entry_type"],
                "size": target_entry["size"],
            }
        )

    copy_items: list[dict] = []
    for normalized_path, source_entry in sorted(source_files.items()):
        target_entry = target_files.get(normalized_path)
        if target_entry and target_entry["signature"] == source_entry["signature"]:
            continue

        if target_entry and target_entry["signature"] != source_entry["signature"]:
            reason = "replace_conflict"
        else:
            reason = "missing_in_target"

        copy_items.append(
            {
                "source_relative_path": source_entry["relative_path"],
                "target_relative_path": source_entry["relative_path"],
                "source_normalized_relative_path": normalized_path,
                "reason": reason,
                "sha256": source_entry["sha256"],
                "link_target": source_entry["link_target"],
                "entry_type": source_entry["entry_type"],
                "size": source_entry["size"],
            }
        )

    summary = {
        "plan_id": plan_id,
        "source_root": str(source_root),
        "target_root": str(target_root),
        "review_root": str(review_root),
        "source_file_count": len(source_files),
        "target_file_count": len(target_files),
        "copy_count": len(copy_items),
        "move_count": len(move_items),
        "kept_count": len(kept_target_paths),
        "unresolved_count": len(unresolved),
    }

    _write_json(dated_dir / "plan_summary.json", summary)
    _write_jsonl(dated_dir / "source_manifest.jsonl", list(source_files.values()))
    _write_jsonl(dated_dir / "target_manifest.jsonl", list(target_files.values()))
    _write_json(
        dated_dir / "copy_to_target.json",
        {
            "plan_id": plan_id,
            "source_root": str(source_root),
            "target_root": str(target_root),
            "items": copy_items,
        },
    )
    _write_json(
        dated_dir / "move_to_review.json",
        {
            "plan_id": plan_id,
            "target_root": str(target_root),
            "review_root": str(review_root),
            "items": move_items,
        },
    )
    _write_json(dated_dir / "unresolved.json", {"plan_id": plan_id, "items": unresolved})
    return dated_dir


def _prune_empty_dirs(root: Path) -> int:
    removed = 0
    for current_root, dirnames, _filenames in os.walk(root, topdown=False):
        current_path = Path(current_root)
        if current_path == root:
            continue
        if dirnames:
            continue
        try:
            next(current_path.iterdir())
            continue
        except StopIteration:
            current_path.rmdir()
            removed += 1
    return removed


def _copy_entry_verified(source_path: Path, target_path: Path, item: dict) -> None:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = target_path.parent / f".{target_path.name}.tmp-{uuid.uuid4().hex}"
    if item["entry_type"] == "symlink":
        os.symlink(item["link_target"], temp_path)
        if os.readlink(temp_path) != item["link_target"]:
            temp_path.unlink(missing_ok=True)
            raise ValueError(f"符号链接复制校验失败: {source_path} -> {target_path}")
    else:
        shutil.copyfile(source_path, temp_path)
        copied_sha256 = _sha256(temp_path)
        if copied_sha256 != item["sha256"]:
            temp_path.unlink(missing_ok=True)
            raise ValueError(f"复制校验失败: {source_path} -> {target_path}")
    temp_path.replace(target_path)


def apply_folder_plan(plan_dir: Path) -> Path:
    plan_dir = Path(plan_dir)
    summary = json.loads((plan_dir / "plan_summary.json").read_text(encoding="utf-8"))
    move_payload = json.loads((plan_dir / "move_to_review.json").read_text(encoding="utf-8"))
    copy_payload = json.loads((plan_dir / "copy_to_target.json").read_text(encoding="utf-8"))

    plan_id = summary["plan_id"]
    source_root = Path(summary["source_root"])
    target_root = Path(summary["target_root"])
    review_root = Path(summary["review_root"])
    review_plan_root = review_root / plan_id
    review_plan_root.mkdir(parents=True, exist_ok=True)

    moved_to_review = 0
    copied_to_target = 0
    guard_failed: list[dict] = []

    for item in move_payload["items"]:
        target_path = target_root / item["target_relative_path"]
        review_path = review_plan_root / item["review_relative_path"]
        if not (target_path.exists() or target_path.is_symlink()) or target_path.is_dir():
            guard_failed.append(
                {
                    "action": "move_to_review",
                    "path": item["target_relative_path"],
                    "reason": "missing_or_not_file",
                }
            )
            continue
        if review_path.exists():
            guard_failed.append(
                {
                    "action": "move_to_review",
                    "path": item["target_relative_path"],
                    "reason": "review_target_exists",
                }
            )
            continue

        review_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.rename(review_path)
        moved_to_review += 1

    for item in copy_payload["items"]:
        source_path = source_root / item["source_relative_path"]
        target_path = target_root / item["target_relative_path"]
        if not (source_path.exists() or source_path.is_symlink()) or (source_path.exists() and source_path.is_dir()):
            guard_failed.append(
                {
                    "action": "copy_to_target",
                    "path": item["source_relative_path"],
                    "reason": "missing_source",
                }
            )
            continue

        if target_path.exists() or target_path.is_symlink():
            if target_path.is_file() or target_path.is_symlink():
                guard_failed.append(
                    {
                        "action": "copy_to_target",
                        "path": item["target_relative_path"],
                        "reason": "target_file_still_exists",
                    }
                )
                continue
            try:
                next(target_path.iterdir())
                guard_failed.append(
                    {
                        "action": "copy_to_target",
                        "path": item["target_relative_path"],
                        "reason": "target_directory_not_empty",
                    }
                )
                continue
            except StopIteration:
                target_path.rmdir()

        _copy_entry_verified(source_path, target_path, item)
        copied_to_target += 1

    pruned_empty_directories = _prune_empty_dirs(target_root)
    receipt = {
        "plan_id": plan_id,
        "source_root": str(source_root),
        "target_root": str(target_root),
        "review_root": str(review_root),
        "review_plan_root": str(review_plan_root),
        "moved_to_review": moved_to_review,
        "copied_to_target": copied_to_target,
        "pruned_empty_directories": pruned_empty_directories,
        "guard_failed": len(guard_failed),
        "guard_failures": guard_failed,
        "status": "success" if not guard_failed else "partial",
    }
    receipt_path = plan_dir / "apply_receipt.json"
    _write_json(receipt_path, receipt)
    return receipt_path

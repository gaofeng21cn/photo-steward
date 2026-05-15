import json
import os
import unicodedata
from pathlib import Path

from tools.icloud_photo_sync.folder_sync import (
    apply_folder_plan,
    normalize_relative_path,
    plan_folder_sync,
)


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_normalize_relative_path_canonicalizes_unicode_equivalents() -> None:
    composed = "项目/プレゼンテーション構成案.md"
    decomposed = unicodedata.normalize("NFD", composed)

    assert normalize_relative_path(composed) == normalize_relative_path(decomposed)


def test_plan_folder_sync_classifies_target_only_duplicate_and_missing(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    target_root = tmp_path / "target"
    review_root = tmp_path / "review"
    logs_root = tmp_path / "logs"

    _write_text(source_root / "01归档" / "keep.txt", "same-content")
    _write_text(source_root / "合作" / "new.txt", "fresh")
    _write_text(target_root / "旧目录" / "keep.txt", "same-content")
    _write_text(target_root / "旧目录" / "orphan.txt", "orphan")

    plan_dir = plan_folder_sync(
        source_root=source_root,
        target_root=target_root,
        review_root=review_root,
        logs_root=logs_root,
        plan_id="todo-plan-1",
    )

    summary = _read_json(plan_dir / "plan_summary.json")
    move_items = _read_json(plan_dir / "move_to_review.json")["items"]
    copy_items = _read_json(plan_dir / "copy_to_target.json")["items"]

    assert summary["plan_id"] == "todo-plan-1"
    assert summary["copy_count"] == 2
    assert summary["move_count"] == 2
    assert summary["unresolved_count"] == 0

    move_map = {item["target_relative_path"]: item for item in move_items}
    assert move_map["旧目录/keep.txt"]["reason"] == "target_only_duplicate_of_source"
    assert move_map["旧目录/keep.txt"]["duplicate_source_paths"] == ["01归档/keep.txt"]
    assert move_map["旧目录/orphan.txt"]["reason"] == "target_only_missing_in_source"

    assert {item["source_relative_path"] for item in copy_items} == {
        "01归档/keep.txt",
        "合作/new.txt",
    }


def test_apply_folder_plan_moves_target_conflict_to_review_then_copies_source(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    target_root = tmp_path / "target"
    review_root = tmp_path / "review"
    logs_root = tmp_path / "logs"

    _write_text(source_root / "合作" / "agenda.md", "authoritative-version")
    _write_text(target_root / "合作" / "agenda.md", "stale-version")
    _write_text(target_root / "旧目录" / "loose.md", "loose")

    plan_dir = plan_folder_sync(
        source_root=source_root,
        target_root=target_root,
        review_root=review_root,
        logs_root=logs_root,
        plan_id="todo-plan-2",
    )

    receipt_path = apply_folder_plan(plan_dir)
    receipt = _read_json(receipt_path)

    assert receipt["plan_id"] == "todo-plan-2"
    assert receipt["moved_to_review"] == 2
    assert receipt["copied_to_target"] == 1
    assert receipt["guard_failed"] == 0
    assert receipt["pruned_empty_directories"] >= 1

    assert (target_root / "合作" / "agenda.md").read_text(encoding="utf-8") == "authoritative-version"
    assert (review_root / "todo-plan-2" / "合作" / "agenda.md").read_text(encoding="utf-8") == "stale-version"
    assert (review_root / "todo-plan-2" / "旧目录" / "loose.md").read_text(encoding="utf-8") == "loose"
    assert not (target_root / "旧目录").exists()


def test_plan_folder_sync_keeps_matching_symlinks_without_unresolved(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    target_root = tmp_path / "target"
    review_root = tmp_path / "review"
    logs_root = tmp_path / "logs"

    source_link = source_root / "AI小红书笔记" / ".venv" / "bin" / "python"
    target_link = target_root / "AI小红书笔记" / ".venv" / "bin" / "python"
    source_link.parent.mkdir(parents=True, exist_ok=True)
    target_link.parent.mkdir(parents=True, exist_ok=True)
    os.symlink("python3.14", source_link)
    os.symlink("python3.14", target_link)

    plan_dir = plan_folder_sync(
        source_root=source_root,
        target_root=target_root,
        review_root=review_root,
        logs_root=logs_root,
        plan_id="todo-plan-symlink",
    )

    summary = _read_json(plan_dir / "plan_summary.json")

    assert summary["source_file_count"] == 1
    assert summary["target_file_count"] == 1
    assert summary["copy_count"] == 0
    assert summary["move_count"] == 0
    assert summary["unresolved_count"] == 0

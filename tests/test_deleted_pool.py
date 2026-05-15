import json
from datetime import date
from pathlib import Path

from tools.icloud_photo_sync.deleted_pool import plan_deleted_pool_prune, prune_deleted_pool


def test_plan_deleted_pool_prune_selects_only_expired_date_roots(tmp_path: Path) -> None:
    deleted_root = tmp_path / "Photos_DeletedFromICloud"
    (deleted_root / "2026-03-01" / "plan-a").mkdir(parents=True)
    (deleted_root / "2026-04-05" / "plan-b").mkdir(parents=True)
    (deleted_root / "not-a-date").mkdir(parents=True)

    candidates = plan_deleted_pool_prune(
        deleted_root=deleted_root,
        retention_days=30,
        today=date(2026, 4, 10),
    )

    assert [candidate.relative_root for candidate in candidates] == ["2026-03-01"]


def test_prune_deleted_pool_deletes_expired_roots_and_writes_receipt(tmp_path: Path) -> None:
    deleted_root = tmp_path / "Photos_DeletedFromICloud"
    logs_root = tmp_path / "Photos_SyncLogs"
    old_root = deleted_root / "2026-03-01" / "plan-a"
    new_root = deleted_root / "2026-04-05" / "plan-b"
    old_root.mkdir(parents=True)
    new_root.mkdir(parents=True)
    (old_root / "sample.txt").write_text("x", encoding="utf-8")

    receipt_path = prune_deleted_pool(
        deleted_root=deleted_root,
        logs_root=logs_root,
        retention_days=30,
        today=date(2026, 4, 10),
        job_id="prune-1",
    )

    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["deleted_roots"] == ["2026-03-01"]
    assert not (deleted_root / "2026-03-01").exists()
    assert (deleted_root / "2026-04-05").exists()


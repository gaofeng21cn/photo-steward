from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CachedFingerprint:
    state_token: str
    sha256: str
    bytes_count: int


class StateStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._initialize()

    def _initialize(self) -> None:
        cursor = self._conn.cursor()
        cursor.executescript(
            """
            CREATE TABLE IF NOT EXISTS resource_cache (
                source_kind TEXT NOT NULL,
                resource_key TEXT NOT NULL,
                state_token TEXT NOT NULL,
                sha256 TEXT NOT NULL,
                bytes_count INTEGER NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (source_kind, resource_key)
            );

            CREATE TABLE IF NOT EXISTS path_bindings (
                resource_key TEXT PRIMARY KEY,
                relative_path TEXT NOT NULL,
                last_plan_id TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS plan_runs (
                plan_id TEXT PRIMARY KEY,
                plan_dir TEXT NOT NULL,
                summary_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                applied_at TEXT
            );

            CREATE TABLE IF NOT EXISTS apply_runs (
                plan_id TEXT PRIMARY KEY,
                receipt_path TEXT NOT NULL,
                summary_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        self._conn.commit()

    def get_cached_fingerprint(
        self,
        source_kind: str,
        resource_key: str,
        state_token: str,
    ) -> CachedFingerprint | None:
        row = self._conn.execute(
            """
            SELECT state_token, sha256, bytes_count
            FROM resource_cache
            WHERE source_kind = ? AND resource_key = ? AND state_token = ?
            """,
            (source_kind, resource_key, state_token),
        ).fetchone()
        if row is None:
            return None
        return CachedFingerprint(
            state_token=row["state_token"],
            sha256=row["sha256"],
            bytes_count=row["bytes_count"],
        )

    def upsert_cached_fingerprint(
        self,
        source_kind: str,
        resource_key: str,
        state_token: str,
        sha256: str,
        bytes_count: int,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO resource_cache (source_kind, resource_key, state_token, sha256, bytes_count)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(source_kind, resource_key)
            DO UPDATE SET
                state_token = excluded.state_token,
                sha256 = excluded.sha256,
                bytes_count = excluded.bytes_count,
                updated_at = CURRENT_TIMESTAMP
            """,
            (source_kind, resource_key, state_token, sha256, bytes_count),
        )
        self._conn.commit()

    def get_binding(self, resource_key: str) -> str | None:
        row = self._conn.execute(
            "SELECT relative_path FROM path_bindings WHERE resource_key = ?",
            (resource_key,),
        ).fetchone()
        return None if row is None else str(row["relative_path"])

    def upsert_binding(self, resource_key: str, relative_path: str, plan_id: str) -> None:
        self._conn.execute(
            """
            INSERT INTO path_bindings (resource_key, relative_path, last_plan_id)
            VALUES (?, ?, ?)
            ON CONFLICT(resource_key)
            DO UPDATE SET
                relative_path = excluded.relative_path,
                last_plan_id = excluded.last_plan_id,
                updated_at = CURRENT_TIMESTAMP
            """,
            (resource_key, relative_path, plan_id),
        )
        self._conn.commit()

    def record_plan(self, plan_id: str, plan_dir: str, summary_json: str) -> None:
        self._conn.execute(
            """
            INSERT INTO plan_runs (plan_id, plan_dir, summary_json)
            VALUES (?, ?, ?)
            ON CONFLICT(plan_id)
            DO UPDATE SET
                plan_dir = excluded.plan_dir,
                summary_json = excluded.summary_json
            """,
            (plan_id, plan_dir, summary_json),
        )
        self._conn.commit()

    def mark_plan_applied(self, plan_id: str) -> None:
        self._conn.execute(
            "UPDATE plan_runs SET applied_at = CURRENT_TIMESTAMP WHERE plan_id = ?",
            (plan_id,),
        )
        self._conn.commit()

    def record_apply(self, plan_id: str, receipt_path: str, summary_json: str) -> None:
        self._conn.execute(
            """
            INSERT INTO apply_runs (plan_id, receipt_path, summary_json)
            VALUES (?, ?, ?)
            ON CONFLICT(plan_id)
            DO UPDATE SET
                receipt_path = excluded.receipt_path,
                summary_json = excluded.summary_json,
                created_at = CURRENT_TIMESTAMP
            """,
            (plan_id, receipt_path, summary_json),
        )
        self._conn.commit()

    def plan_exists(self, plan_id: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM plan_runs WHERE plan_id = ?",
            (plan_id,),
        ).fetchone()
        return row is not None

    def close(self) -> None:
        self._conn.close()

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .state import StateStore
from .utils import file_state_token, sha256_file


@dataclass(frozen=True)
class FingerprintResult:
    sha256: str
    bytes_count: int
    state_token: str


class FingerprintService:
    def __init__(
        self,
        store: StateStore,
        hasher: Callable[[Path], str] | None = None,
    ) -> None:
        self.store = store
        self.hasher = hasher or sha256_file

    def fingerprint_path(self, source_kind: str, resource_key: str, path: Path) -> FingerprintResult:
        token = file_state_token(path)
        cached = self.store.get_cached_fingerprint(source_kind, resource_key, token)
        if cached is not None:
            return FingerprintResult(
                sha256=cached.sha256,
                bytes_count=cached.bytes_count,
                state_token=token,
            )

        sha256 = self.hasher(path)
        bytes_count = path.stat().st_size
        self.store.upsert_cached_fingerprint(
            source_kind=source_kind,
            resource_key=resource_key,
            state_token=token,
            sha256=sha256,
            bytes_count=bytes_count,
        )
        return FingerprintResult(sha256=sha256, bytes_count=bytes_count, state_token=token)

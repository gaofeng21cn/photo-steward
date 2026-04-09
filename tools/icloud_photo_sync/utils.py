from __future__ import annotations

import hashlib
from pathlib import Path


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def file_state_token(path: Path) -> str:
    stat = path.stat()
    return f"{stat.st_size}:{stat.st_mtime_ns}:{stat.st_ctime_ns}"


def normalize_filename(name: str) -> str:
    cleaned = name.replace("/", "_").replace("\x00", "").strip()
    return cleaned or "unnamed"

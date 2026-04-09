from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class ICloudResource:
    resource_key: str
    asset_uuid: str
    asset_local_identifier: str
    resource_index: int
    original_filename: str
    created_at: str
    sha256: str
    bytes_count: int
    source_kind: str
    source_path: str | None = None
    source_state_token: str | None = None

    def to_manifest_dict(self) -> dict:
        payload = asdict(self)
        payload["bytes"] = payload.pop("bytes_count")
        return payload


@dataclass(frozen=True)
class NasFile:
    relative_path: str
    absolute_path: str
    sha256: str
    bytes_count: int
    state_token: str

    def to_manifest_dict(self) -> dict:
        payload = asdict(self)
        payload["bytes"] = payload.pop("bytes_count")
        return payload


@dataclass(frozen=True)
class MirrorAction:
    resource_key: str
    asset_local_identifier: str
    resource_index: int
    original_filename: str
    target_relative_path: str
    sha256: str
    bytes_count: int
    source_kind: str
    source_path: str | None
    source_state_token: str | None

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["bytes"] = payload.pop("bytes_count")
        return payload


@dataclass(frozen=True)
class DeleteAction:
    relative_path: str
    sha256: str
    bytes_count: int
    state_token: str

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["bytes"] = payload.pop("bytes_count")
        return payload


@dataclass
class SyncPlan:
    plan_id: str
    mirror_actions: list[MirrorAction] = field(default_factory=list)
    delete_actions: list[DeleteAction] = field(default_factory=list)
    bindings: dict[str, str] = field(default_factory=dict)
    unresolved: list[dict] = field(default_factory=list)

    def summary(self) -> dict:
        return {
            "plan_id": self.plan_id,
            "mirror_count": len(self.mirror_actions),
            "delete_count": len(self.delete_actions),
            "unresolved_count": len(self.unresolved),
            "binding_count": len(self.bindings),
        }

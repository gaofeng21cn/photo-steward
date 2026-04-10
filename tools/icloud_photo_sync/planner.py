from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from pathlib import PurePosixPath

from .models import DeleteAction, ICloudResource, MirrorAction, NasFile, SyncPlan
from .utils import normalize_filename


def _resource_sort_key(resource: ICloudResource) -> tuple[str, str]:
    return (resource.created_at, resource.resource_key)


def _preferred_parent(created_at: str) -> str:
    try:
        dt = datetime.fromisoformat(created_at)
    except ValueError:
        return "unknown/00"
    return f"{dt:%Y}/{dt:%m}"


def _pick_existing_candidate(resource: ICloudResource, candidates: list[NasFile]) -> NasFile:
    desired_parent = _preferred_parent(resource.created_at)
    desired_name = normalize_filename(resource.original_filename)

    def score(item: NasFile) -> tuple[int, int, str]:
        path = PurePosixPath(item.relative_path)
        parent = str(path.parent)
        basename = path.name
        return (
            0 if parent == desired_parent else 1,
            0 if basename == desired_name else 1,
            item.relative_path,
        )

    return sorted(candidates, key=score)[0]


def _bound_path_requires_relocation(resource: ICloudResource, relative_path: str) -> bool:
    return str(PurePosixPath(relative_path).parent) != _preferred_parent(resource.created_at)


def _allocate_path(resource: ICloudResource, reserved_paths: set[str]) -> str:
    parent = _preferred_parent(resource.created_at)
    filename = normalize_filename(resource.original_filename)
    base = PurePosixPath(parent) / filename
    if str(base) not in reserved_paths:
        return str(base)

    stem = base.stem
    suffix = base.suffix
    index = 1
    while True:
        candidate = base.with_name(f"{stem}__dup{index}{suffix}")
        if str(candidate) not in reserved_paths:
            return str(candidate)
        index += 1


def build_sync_plan(
    icloud_resources: list[ICloudResource],
    nas_files: list[NasFile],
    existing_bindings: dict[str, str],
    plan_id: str,
) -> SyncPlan:
    plan = SyncPlan(plan_id=plan_id)
    nas_by_rel = {item.relative_path: item for item in nas_files}
    unmatched_nas_by_hash: dict[str, list[NasFile]] = defaultdict(list)
    matched_nas_paths: set[str] = set()
    stale_bound_paths: set[str] = set()
    unmatched_resources: list[ICloudResource] = []

    for item in nas_files:
        unmatched_nas_by_hash[item.sha256].append(item)
    for bucket in unmatched_nas_by_hash.values():
        bucket.sort(key=lambda item: item.relative_path)

    for resource in sorted(icloud_resources, key=_resource_sort_key):
        bound_path = existing_bindings.get(resource.resource_key)
        if bound_path:
            current = nas_by_rel.get(bound_path)
            if current is not None and current.sha256 == resource.sha256:
                if _bound_path_requires_relocation(resource, current.relative_path):
                    stale_bound_paths.add(current.relative_path)
                    unmatched_resources.append(resource)
                    continue
                matched_nas_paths.add(current.relative_path)
                plan.bindings[resource.resource_key] = current.relative_path
                continue
        unmatched_resources.append(resource)

    still_unmatched: list[ICloudResource] = []
    for resource in unmatched_resources:
        candidates = [
            item
            for item in unmatched_nas_by_hash.get(resource.sha256, [])
            if item.relative_path not in matched_nas_paths and item.relative_path not in stale_bound_paths
        ]
        if not candidates:
            still_unmatched.append(resource)
            continue
        selected = _pick_existing_candidate(resource, candidates)
        matched_nas_paths.add(selected.relative_path)
        plan.bindings[resource.resource_key] = selected.relative_path

    reserved_paths = set(matched_nas_paths)
    for resource in sorted(still_unmatched, key=_resource_sort_key):
        target_path = _allocate_path(resource, reserved_paths)
        reserved_paths.add(target_path)
        plan.bindings[resource.resource_key] = target_path
        current = nas_by_rel.get(target_path)
        if current is None or current.sha256 != resource.sha256:
            plan.mirror_actions.append(
                MirrorAction(
                    resource_key=resource.resource_key,
                    asset_local_identifier=resource.asset_local_identifier,
                    resource_index=resource.resource_index,
                    original_filename=resource.original_filename,
                    target_relative_path=target_path,
                    sha256=resource.sha256,
                    bytes_count=resource.bytes_count,
                    source_kind=resource.source_kind,
                    source_path=resource.source_path,
                    source_state_token=resource.source_state_token,
                )
            )
        else:
            matched_nas_paths.add(current.relative_path)

    for item in nas_files:
        if item.relative_path in matched_nas_paths:
            continue
        plan.delete_actions.append(
            DeleteAction(
                relative_path=item.relative_path,
                sha256=item.sha256,
                bytes_count=item.bytes_count,
                state_token=item.state_token,
            )
        )

    return plan

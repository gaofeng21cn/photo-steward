from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from .apply import execute_apply
from .fingerprint import FingerprintService
from .models import ICloudResource, NasFile, SyncPlan
from .photos_bridge import PhotosBridge, PhotosResourceDescriptor
from .photos_db import AssetMeta, load_asset_index
from .planner import build_sync_plan
from .state import StateStore
from .utils import normalize_filename


def _json_dumps(payload: dict | list) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def _json_lines(path: Path, items: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for item in items:
            handle.write(json.dumps(item, ensure_ascii=False))
            handle.write("\n")


def _metadata_state_token(descriptor: PhotosResourceDescriptor) -> str:
    payload = {
        "asset_local_identifier": descriptor.asset_local_identifier,
        "creation_date": descriptor.creation_date,
        "file_size": descriptor.file_size,
        "modification_date": descriptor.modification_date,
        "original_filename": descriptor.original_filename,
        "resource_index": descriptor.resource_index,
        "resource_type": descriptor.resource_type,
        "uti": descriptor.uniform_type_identifier,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def _default_plan_id() -> str:
    return datetime.now().astimezone().strftime("plan-%Y%m%dT%H%M%S")


def select_primary_media_resources(descriptors: list[PhotosResourceDescriptor]) -> list[PhotosResourceDescriptor]:
    by_asset: dict[str, list[PhotosResourceDescriptor]] = {}
    for descriptor in descriptors:
        by_asset.setdefault(descriptor.asset_uuid, []).append(descriptor)

    selected: list[PhotosResourceDescriptor] = []
    primary_photo_priority = [1, 5, 4]
    primary_video_priority = [2, 6]
    paired_video_priority = [9, 10]

    for asset_uuid in sorted(by_asset):
        bucket = sorted(by_asset[asset_uuid], key=lambda item: (item.resource_index, item.original_filename))
        media_type = bucket[0].media_type
        media_subtypes = bucket[0].media_subtypes

        def pick_by_priority(priorities: list[int]) -> PhotosResourceDescriptor | None:
            for resource_type in priorities:
                for item in bucket:
                    if item.resource_type == resource_type:
                        return item
            return None

        if media_type == 2:
            primary_video = pick_by_priority(primary_video_priority)
            if primary_video is not None:
                selected.append(primary_video)
            continue

        primary_photo = pick_by_priority(primary_photo_priority)
        if primary_photo is not None:
            selected.append(primary_photo)

        # Live Photo stills carry a paired MOV as an extra user-visible resource.
        if media_subtypes != 0:
            paired_video = pick_by_priority(paired_video_priority)
            if paired_video is not None:
                selected.append(paired_video)

    return selected


def _iter_nas_files(nas_root: Path, fingerprinter: FingerprintService) -> list[NasFile]:
    files: list[NasFile] = []
    scanned = 0
    for dirpath, dirnames, filenames in os.walk(nas_root):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        for filename in sorted(name for name in filenames if not name.startswith(".")):
            path = Path(dirpath) / filename
            if not path.is_file():
                continue
            relative_path = str(path.relative_to(nas_root))
            fingerprint = fingerprinter.fingerprint_path("nas", relative_path, path)
            files.append(
                NasFile(
                    relative_path=relative_path,
                    absolute_path=str(path),
                    sha256=fingerprint.sha256,
                    bytes_count=fingerprint.bytes_count,
                    state_token=fingerprint.state_token,
                )
            )
            scanned += 1
            if scanned % 2000 == 0:
                print(
                    json.dumps(
                        {
                            "stage": "scan_nas_progress",
                            "scanned": scanned,
                        },
                        ensure_ascii=False,
                    ),
                    flush=True,
                )
    return files


def _build_icloud_resources(
    asset_index: dict[str, AssetMeta],
    resource_descriptors: list[PhotosResourceDescriptor],
    fingerprinter: FingerprintService,
    bridge: PhotosBridge,
    store: StateStore,
    stage_dir: Path,
) -> tuple[list[ICloudResource], list[dict]]:
    grouped: dict[str, list[PhotosResourceDescriptor]] = {}
    for descriptor in resource_descriptors:
        grouped.setdefault(descriptor.asset_uuid, []).append(descriptor)

    results: list[ICloudResource] = []
    unresolved: list[dict] = []
    pending_exports: list[dict] = []

    def emit_progress() -> None:
        if len(results) % 500 == 0 and results:
            print(
                json.dumps(
                    {
                        "stage": "icloud_resource_progress",
                        "resolved_count": len(results),
                        "unresolved_count": len(unresolved),
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )

    for asset_uuid, descriptors in sorted(grouped.items()):
        descriptors.sort(key=lambda item: item.resource_index)
        meta = asset_index.get(asset_uuid)
        local_primary_path = Path(meta.local_primary_path) if meta and meta.local_primary_path else None
        local_primary_consumed = False

        for descriptor in descriptors:
            resource_key = descriptor.resource_key
            created_at = (
                (meta.created_at if meta else None)
                or descriptor.creation_date
                or descriptor.modification_date
                or datetime.now().astimezone().isoformat()
            )

            try:
                if (
                    local_primary_path
                    and local_primary_path.exists()
                    and not local_primary_consumed
                    and normalize_filename(local_primary_path.name) == normalize_filename(descriptor.original_filename)
                ):
                    fingerprint = fingerprinter.fingerprint_path("icloud_local", resource_key, local_primary_path)
                    results.append(
                        ICloudResource(
                            resource_key=resource_key,
                            asset_uuid=descriptor.asset_uuid,
                            asset_local_identifier=descriptor.asset_local_identifier,
                            resource_index=descriptor.resource_index,
                            original_filename=descriptor.original_filename,
                            created_at=created_at,
                            sha256=fingerprint.sha256,
                            bytes_count=fingerprint.bytes_count,
                            source_kind="local_file",
                            source_path=str(local_primary_path),
                            source_state_token=fingerprint.state_token,
                    )
                    )
                    local_primary_consumed = True
                    emit_progress()
                    continue

                state_token = _metadata_state_token(descriptor)
                cached = store.get_cached_fingerprint("icloud_resource", resource_key, state_token)
                if cached is not None:
                    sha256 = cached.sha256
                    bytes_count = cached.bytes_count
                    results.append(
                        ICloudResource(
                            resource_key=resource_key,
                            asset_uuid=descriptor.asset_uuid,
                            asset_local_identifier=descriptor.asset_local_identifier,
                            resource_index=descriptor.resource_index,
                            original_filename=descriptor.original_filename,
                            created_at=created_at,
                            sha256=sha256,
                            bytes_count=bytes_count,
                            source_kind="photos_resource_export",
                            source_state_token=state_token,
                        )
                    )
                    emit_progress()
                    continue

                export_path = stage_dir / f"{descriptor.asset_uuid}_{descriptor.resource_index}_{normalize_filename(descriptor.original_filename)}"
                pending_exports.append(
                    {
                        "resource_key": resource_key,
                        "asset_uuid": descriptor.asset_uuid,
                        "asset_local_identifier": descriptor.asset_local_identifier,
                        "resource_index": descriptor.resource_index,
                        "original_filename": descriptor.original_filename,
                        "created_at": created_at,
                        "state_token": state_token,
                        "request_id": resource_key,
                        "output_path": str(export_path),
                    }
                )
            except Exception as exc:  # noqa: BLE001
                unresolved.append(
                    {
                        "kind": "icloud_resource_unresolved",
                        "asset_uuid": descriptor.asset_uuid,
                        "asset_local_identifier": descriptor.asset_local_identifier,
                        "resource_index": descriptor.resource_index,
                        "original_filename": descriptor.original_filename,
                        "error": str(exc),
                    }
                )

    batch_size = 25
    for batch_start in range(0, len(pending_exports), batch_size):
        batch = pending_exports[batch_start : batch_start + batch_size]
        responses = bridge.export_resources_batch(
            [
                {
                    "request_id": item["request_id"],
                    "asset_local_identifier": item["asset_local_identifier"],
                    "resource_index": item["resource_index"],
                    "output_path": item["output_path"],
                }
                for item in batch
            ]
        )
        for item in batch:
            payload = responses.get(item["request_id"])
            if payload is None or payload.get("error"):
                unresolved.append(
                    {
                        "kind": "icloud_resource_unresolved",
                        "asset_uuid": item["asset_uuid"],
                        "asset_local_identifier": item["asset_local_identifier"],
                        "resource_index": item["resource_index"],
                        "original_filename": item["original_filename"],
                        "error": None if payload is None else payload.get("error"),
                    }
                )
                continue

            exported = Path(payload["output_path"])
            fingerprint = fingerprinter.fingerprint_path("icloud_export", item["resource_key"], exported)
            store.upsert_cached_fingerprint(
                source_kind="icloud_resource",
                resource_key=item["resource_key"],
                state_token=item["state_token"],
                sha256=fingerprint.sha256,
                bytes_count=fingerprint.bytes_count,
            )
            results.append(
                ICloudResource(
                    resource_key=item["resource_key"],
                    asset_uuid=item["asset_uuid"],
                    asset_local_identifier=item["asset_local_identifier"],
                    resource_index=item["resource_index"],
                    original_filename=item["original_filename"],
                    created_at=item["created_at"],
                    sha256=fingerprint.sha256,
                    bytes_count=fingerprint.bytes_count,
                    source_kind="photos_resource_export",
                    source_state_token=item["state_token"],
                )
            )
            exported.unlink(missing_ok=True)
            emit_progress()

    return results, unresolved


def persist_plan_bundle(
    plan_dir: Path,
    plan: SyncPlan,
    icloud_resources: list[ICloudResource],
    nas_files: list[NasFile],
    unresolved: list[dict],
) -> None:
    plan_dir.mkdir(parents=True, exist_ok=True)
    summary = plan.summary()
    summary["unresolved_count"] = len(unresolved)

    (plan_dir / "plan_summary.json").write_text(_json_dumps(summary), encoding="utf-8")
    _json_lines(
        plan_dir / "present_in_icloud_manifest.jsonl",
        [item.to_manifest_dict() for item in icloud_resources],
    )
    _json_lines(
        plan_dir / "present_in_nas_manifest.jsonl",
        [item.to_manifest_dict() for item in nas_files],
    )
    (plan_dir / "mirror_to_nas.json").write_text(
        _json_dumps({"plan_id": plan.plan_id, "items": [item.to_dict() for item in plan.mirror_actions]}),
        encoding="utf-8",
    )
    (plan_dir / "move_to_nas_deleted_pool.json").write_text(
        _json_dumps({"plan_id": plan.plan_id, "items": [item.to_dict() for item in plan.delete_actions]}),
        encoding="utf-8",
    )
    (plan_dir / "unresolved.json").write_text(
        _json_dumps({"plan_id": plan.plan_id, "items": unresolved}),
        encoding="utf-8",
    )


def run_plan(
    *,
    library_path: Path,
    db_path: Path,
    nas_root: Path,
    logs_root: Path,
    state_db: Path,
    stage_dir: Path,
    swift_source: Path,
    plan_id: str | None = None,
) -> Path:
    plan_id = plan_id or _default_plan_id()
    dated_dir = logs_root / datetime.now().astimezone().strftime("%Y-%m-%d") / plan_id

    print(json.dumps({"stage": "plan_start", "plan_id": plan_id}, ensure_ascii=False), flush=True)
    store = StateStore(state_db)
    fingerprinter = FingerprintService(store)
    bridge = PhotosBridge(swift_source=swift_source, build_dir=state_db.parent / "bin")

    print(json.dumps({"stage": "load_asset_index"}, ensure_ascii=False), flush=True)
    asset_index = load_asset_index(library_path=library_path, db_path=db_path)
    print(json.dumps({"stage": "list_photos_resources"}, ensure_ascii=False), flush=True)
    all_resource_descriptors = bridge.list_resources()
    resource_descriptors = select_primary_media_resources(all_resource_descriptors)
    print(
        json.dumps(
            {
                "stage": "photos_resources_listed",
                "asset_count": len(asset_index),
                "resource_count_all": len(all_resource_descriptors),
                "resource_count_selected": len(resource_descriptors),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    stage_dir.mkdir(parents=True, exist_ok=True)

    with TemporaryDirectory(prefix=f"{plan_id}-", dir=stage_dir) as temp_stage:
        icloud_resources, unresolved = _build_icloud_resources(
            asset_index=asset_index,
            resource_descriptors=resource_descriptors,
            fingerprinter=fingerprinter,
            bridge=bridge,
            store=store,
            stage_dir=Path(temp_stage),
        )
    print(
        json.dumps(
            {
                "stage": "icloud_resources_materialized",
                "resolved_count": len(icloud_resources),
                "unresolved_count": len(unresolved),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )

    print(json.dumps({"stage": "scan_nas"}, ensure_ascii=False), flush=True)
    nas_files = _iter_nas_files(nas_root, fingerprinter)
    print(
        json.dumps(
            {
                "stage": "nas_scanned",
                "nas_file_count": len(nas_files),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    existing_bindings = {
        resource.resource_key: store.get_binding(resource.resource_key)
        for resource in icloud_resources
        if store.get_binding(resource.resource_key)
    }
    plan = build_sync_plan(
        icloud_resources=icloud_resources,
        nas_files=nas_files,
        existing_bindings=existing_bindings,
        plan_id=plan_id,
    )

    persist_plan_bundle(
        plan_dir=dated_dir,
        plan=plan,
        icloud_resources=icloud_resources,
        nas_files=nas_files,
        unresolved=unresolved,
    )

    for resource_key, relative_path in plan.bindings.items():
        store.upsert_binding(resource_key, relative_path, plan_id)
    store.record_plan(plan_id, str(dated_dir), json.dumps(plan.summary(), ensure_ascii=False))
    store.close()
    print(
        json.dumps(
            {
                "stage": "plan_done",
                "plan_dir": str(dated_dir),
                **plan.summary(),
                "unresolved_count": len(unresolved),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    return dated_dir


def run_apply(
    *,
    plan_dir: Path,
    nas_root: Path,
    deleted_root: Path,
    state_db: Path,
    swift_source: Path,
) -> Path:
    store = StateStore(state_db)
    bridge = PhotosBridge(swift_source=swift_source, build_dir=state_db.parent / "bin")

    class PhotosPlanExporter:
        def __call__(self, action: dict, temp_root: Path) -> Path:
            filename = normalize_filename(action["original_filename"])
            output_path = temp_root / f"{action['resource_key'].replace('/', '_')}__{filename}"
            return bridge.export_resource(action["asset_local_identifier"], int(action["resource_index"]), output_path)

        def export_batch(self, actions: list[dict], temp_root: Path) -> dict[str, Path]:
            if not actions:
                return {}
            requests = []
            for action in actions:
                filename = normalize_filename(action["original_filename"])
                output_path = temp_root / f"{action['resource_key'].replace('/', '_')}__{filename}"
                requests.append(
                    {
                        "request_id": action["resource_key"],
                        "asset_local_identifier": action["asset_local_identifier"],
                        "resource_index": int(action["resource_index"]),
                        "output_path": str(output_path),
                    }
                )
            responses = bridge.export_resources_batch(requests)
            exported: dict[str, Path] = {}
            for action in actions:
                payload = responses.get(action["resource_key"])
                if payload is None or payload.get("error"):
                    continue
                exported[action["resource_key"]] = Path(payload["output_path"])
            return exported

    print(json.dumps({"stage": "apply_start", "plan_dir": str(plan_dir)}, ensure_ascii=False), flush=True)
    receipt = execute_apply(
        plan_dir=plan_dir,
        nas_root=nas_root,
        deleted_root=deleted_root,
        exporter=PhotosPlanExporter(),
    )
    receipt_path = Path(plan_dir) / "apply_receipt.json"
    store.record_apply(receipt["plan_id"], str(receipt_path), json.dumps(receipt, ensure_ascii=False))
    store.mark_plan_applied(receipt["plan_id"])
    store.close()
    print(json.dumps({"stage": "apply_done", "receipt_path": str(receipt_path), **receipt}, ensure_ascii=False), flush=True)
    return receipt_path

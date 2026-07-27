# Product Architecture

## Product identity

`icloud-photo-sync` is the local synchronization service for an iCloud-centered
photo hub:

- iCloud Photos is the authoritative library and multi-device ingest surface.
- NAS is the current file mirror and deletion quarantine.
- OneDrive is an off-site copy, not an authority.
- Time Machine protects the local Photos library, database, and downloaded
  originals.

The product is AI-first at the control plane and deterministic at the data
plane. Exact resource identity, copy, relocation, quarantine, and retention use
Photos metadata, stable resource keys, dates, SHA-256, and guarded receipts. AI
may explain differences, organize review, and recommend actions, but it must not
be the sole authority for overwrite or deletion.

## User surfaces

The intended product has three layers that share one contract:

1. The local service and CLI own deterministic operations and receipts.
2. A Codex Skill is the primary conversational interface for inspect, plan,
   explain, review, and explicitly approved apply operations.
3. An optional macOS menu bar app displays health, mount identity, last attempt,
   last success, counts, progress, and pending plans. It invokes the service
   instead of reimplementing synchronization.

The stable machine-readable interfaces are:

```bash
icloud-photo-sync preflight
icloud-photo-sync status --scope photo --format json
icloud-photo-sync plan-job
icloud-photo-sync apply-job --plan-dir <reviewed-plan>
```

## Core boundaries

Retain in the photo core:

- Photos.framework Swift bridge for iCloud-only and Live Photo resources
- resource selection and manifest generation
- SHA-256 identity and SQLite fingerprint cache
- proposed plan, guarded apply, and applied binding state
- NAS mirror, iCloud deletion quarantine, and retention receipts
- backup adapter and launchd automation

Relocate out of the core:

- `folder_sync` and ToDo automation belong to a generic guarded folder-sync
  capability. They may remain here until that capability has a separate owner,
  but their status and automation surfaces stay separate.
- `google_review` contains historical migration rules. It should be archived as
  a migration tool after its remaining operational need is confirmed.

## Dependency decisions

- Keep the small Photos Swift bridge. Generic file sync tools cannot reproduce
  Photos resource and Live Photo semantics.
- Keep standard-library SQLite and SHA-256. SQLAlchemy and a database service
  would add complexity without improving this single-user workload.
- Keep `launchd`; it is the macOS-native scheduler.
- Keep guarded photo plan/apply logic. `rsync`, Syncthing, and rclone do not
  implement authoritative-source, date relocation, and quarantine rules.
- Replace local File Provider-only OneDrive proof with `rclone copy` plus remote
  readback when remote credentials are configured. Local `rsync` success only
  proves that File Provider accepted local bytes.
- Retire direct reads of Apple private Photos SQLite tables or move them behind
  a maintained compatibility adapter. Photos.framework remains the authority.

## State contract

- A plan writes proposed bindings; it does not mutate applied bindings.
- Only an apply receipt with `status=success` commits bindings and marks a plan
  applied.
- `partial` and failed receipts remain pending and return a non-zero job result.
- Latest status records last attempt, last success, consecutive failures,
  pending plan, and the actual NAS mount source.
- `latest_photo_overview.md` and `latest_todo_overview.md` are projections, not
  sources of truth.

## Delivery sequence

1. Stabilize the local service contract and live automation.
2. Package a professional Codex Skill around the stable CLI and JSON status.
3. Build the menu bar app as a read-mostly control console.
4. Add verified OneDrive remote readback.
5. Relocate generic folder sync and archive historical migration code.

The menu bar app should not start before steps 1 and 2 are stable; otherwise the
same lifecycle bugs would be duplicated into a second implementation.

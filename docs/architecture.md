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
3. An optional macOS app pairs a compact menu bar entry point with a main
   control-console window. It displays health, mount identity, last attempt,
   last success, counts, pending plans, and execution state; it invokes the
   service instead of reimplementing synchronization.

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
- Route scheduled jobs directly through the existing wrappers so the
  Photos.framework bridge keeps a stable launchd execution context. The menu
  bar app remains an interactive console and does not own scheduled execution
  or duplicate synchronization logic.
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
- Scheduled preflight timeouts and NAS traversal errors are terminal failures;
  they preserve the last success instead of producing an empty-NAS plan.
- `latest_photo_overview.md` and `latest_todo_overview.md` are projections, not
  sources of truth.

## Current delivery state

The first three product layers are implemented and installed from the
canonical repository:

1. The local service and CLI provide the deterministic data plane.
2. `skills/icloud-photo-center` is the Codex conversational control plane.
3. `app/PhotoCenterMenuBar` is a thin macOS interaction layer: the menu bar
   provides health and quick actions, while the control-console window provides
   status, plan review, and confirmed Apply.

The remaining architecture work is bounded follow-up, not a missing user
surface:

4. Add verified OneDrive remote readback.
5. Relocate generic folder sync and archive historical migration code.

The app remains intentionally thin. It reads the JSON status contract, starts
the CLI for manual plan generation, and applies only the exact pending plan
after an in-app confirmation. Its main window separates overview, pending-plan
review, and activity rather than treating a small menu bar panel as the full
control surface. `launchd` remains outside the app process and only performs
scheduled plan discovery, retention, and backup. The app does not contain a
second copy of the synchronization rules.

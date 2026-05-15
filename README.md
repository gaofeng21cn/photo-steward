<p align="center">
  <strong>English</strong> | <a href="./README.zh-CN.md">中文</a>
</p>

<h1 align="center">icloud-photo-sync</h1>

<p align="center"><strong>Guarded iCloud Photos to NAS mirroring, plus authoritative folder syncing for iCloud-managed workspaces</strong></p>
<p align="center">Planning Before Mutation · SHA-First Matching · Automated Plan With Manual Apply</p>

<table>
  <tr>
    <td width="33%" valign="top">
      <strong>Primary Use</strong><br/>
      Mirror <code>iCloud Photos</code> into a NAS library, and align selected iCloud folders such as <code>ToDo</code> into backup clouds without changing the source of truth
    </td>
    <td width="33%" valign="top">
      <strong>Interface</strong><br/>
      Python CLI plus shell wrappers, with optional <code>launchd</code> jobs for scheduled planning, deleted-pool retention, and OneDrive backup
    </td>
    <td width="33%" valign="top">
      <strong>Safety Model</strong><br/>
      <code>plan</code> can run automatically, <code>apply</code> stays explicit, and NAS deletions move into a reviewed holding area
    </td>
  </tr>
</table>

> Publicly, `icloud-photo-sync` started as a local-first mirror tool for `iCloud Photos -> NAS`. It now also carries a guarded folder-sync surface for `iCloud authoritative -> backup mirror` workflows such as `Documents/ToDo -> OneDrive/ToDo`.

## Product Position

Use this repository when `iCloud Photos` is your only source of truth, `NAS` is the mirror that should follow it, and you want repeatable file-level synchronization instead of ad hoc export-and-copy routines.

This repository is intentionally narrower than a generic photo manager:

- `iCloud Photos` is the authoritative library
- the NAS is the mirror target, not the daily editing surface
- `OneDrive` or similar tools can remain backup relays, but they do not decide what is current
- selected workspace folders can follow the same `plan -> apply -> review pool` contract instead of ad hoc drag-and-drop syncing

## What It Helps You Do

- Build a `plan` from the current Photos library, NAS contents, and persisted sync state.
- Copy new or missing iCloud assets into the NAS mirror.
- Detect NAS-only items after they disappear from iCloud and move them into `/Volumes/home/Photos_DeletedFromICloud` instead of hard-deleting them.
- Keep all operational receipts under `/Volumes/home/Photos_SyncLogs/YYYY-MM-DD/<plan_id>/`.
- Run scheduled discovery without giving scheduled jobs permission to mutate the NAS directly.
- Build a strict `folder-plan` for an authoritative local folder and move `mirror-only` residues into a review pool before copying the source view into place.

## Quick Start

Run from the repository root:

```bash
python3 -m tools.icloud_photo_sync.cli plan
python3 -m tools.icloud_photo_sync.cli apply --plan-dir /Volumes/home/Photos_SyncLogs/YYYY-MM-DD/<plan_id>
python3 -m tools.icloud_photo_sync.cli plan-job
python3 -m tools.icloud_photo_sync.cli todo-plan-job
python3 -m tools.icloud_photo_sync.cli prune-deleted-pool --dry-run
python3 -m tools.icloud_photo_sync.cli backup-onedrive --dry-run
python3 -m tools.icloud_photo_sync.cli todo-plan
python3 -m tools.icloud_photo_sync.cli todo-apply --plan-dir state/folder_sync_logs/YYYY-MM-DD/<plan_id>
```

Wrapper scripts are provided for the common path:

```bash
./scripts/run_plan.sh
./scripts/run_todo_plan.sh
./scripts/run_apply_latest.sh --plan-dir /Volumes/home/Photos_SyncLogs/YYYY-MM-DD/<plan_id>
./scripts/run_apply_latest.sh --latest
./scripts/run_deleted_pool_retention.sh --dry-run
./scripts/run_onedrive_backup.sh --dry-run
./scripts/install_launchd_agents.sh
```

## Runtime Layout

Repository-tracked content stays small and stable:

- source code under `tools/icloud_photo_sync/`
- tests under `tests/`
- operational docs under `docs/`

Runtime state stays outside Git intent even when some paths live inside the repo working tree:

- state DB: `state/icloud-photo-sync/state.sqlite3`
- latest job status: `state/status/latest_*.json`
- latest overview: `state/status/latest_overview.md`
- staging directory: `tmp/icloud_photo_sync_stage`
- sync logs: `/Volumes/home/Photos_SyncLogs`
- generic folder sync logs: `state/folder_sync_logs`
- NAS deleted pool: `/Volumes/home/Photos_DeletedFromICloud`
- OneDrive backup root: `/Users/gaofeng/OneDrive/Backup/icloud-photo-sync`
- ToDo review pool: `/Users/gaofeng/Library/CloudStorage/OneDrive-个人/ToDo_OneDriveOnlyReview/<plan_id>/`

## Automation Model

The recommended automation policy is intentionally asymmetric and layered:

- automate `plan-job`
- automate `todo-plan-job`
- automate deleted-pool retention
- automate OneDrive backup from NAS
- keep `apply` manual
- review the generated plan or the latest plan directory before mutating the NAS

That keeps daily discovery cheap while preserving a hard gate before file copies and deletion moves.

The default scheduled jobs installed by `./scripts/install_launchd_agents.sh` are:

- `com.gaofeng.icloud-photo-sync.plan.daily` at `03:15`
- `com.gaofeng.icloud-photo-sync.deleted-pool.daily` at `04:00`
- `com.gaofeng.icloud-photo-sync.onedrive.daily` at `04:15`
- `com.gaofeng.icloud-photo-sync.todo.daily` at `04:30`

All three jobs write stdout/stderr under `tmp/automation/`.

## Current Boundaries

- The current implementation is built around macOS Photos library access and the bundled Swift bridge.
- Matching is strict and content-oriented; the workflow does not rely on fuzzy heuristics to collapse near-duplicates.
- NAS-side deletions are implemented as audited moves into a holding area, not immediate destructive removal.
- Folder sync remains source-authoritative: target-only residues move into a review pool, and only then does the source view get copied into the mirror.
- This repository is a sync tool, not a general DAM, cloud backend, or gallery UI.

## For Agents

Operate this repository through the CLI and wrapper scripts instead of re-implementing the sync logic.

Typical agent tasks:

- run `plan`
- run `plan-job` and inspect `state/status/latest_plan.json`
- run `todo-plan-job` and inspect `state/status/latest_todo_plan.json`
- inspect the generated receipts
- run `apply` for an explicitly selected plan directory
- run `todo-plan` to align `/Users/gaofeng/Documents/ToDo` against `OneDrive/ToDo`
- inspect `state/folder_sync_logs/YYYY-MM-DD/<plan_id>/`
- run `todo-apply` only for the reviewed plan directory
- run `prune-deleted-pool` or `backup-onedrive` in dry-run mode
- install or audit the scheduled automation set

## Documentation

- [Automation guide](docs/automation.md)
- [Authoritative workflow notes](docs/icloud-photo-authoritative-workflow.md)
- [Design spec](docs/specs/2026-04-09-icloud-photo-sync-design.md)
- [Implementation plan](docs/plans/2026-04-09-icloud-photo-sync.md)
- [ToDo authoritative sync design](docs/specs/2026-04-10-icloud-todo-onedrive-design.md)
- [ToDo authoritative sync implementation plan](docs/plans/2026-04-10-icloud-todo-onedrive.md)

The detailed docs are currently Chinese-first because the active operator surface is personal and local.

## Technical Validation

```bash
python3 -m pytest tests -q
```

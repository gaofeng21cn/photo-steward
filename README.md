<p align="center">
  <strong>English</strong> | <a href="./README.zh-CN.md">中文</a>
</p>

<h1 align="center">icloud-photo-sync</h1>

<p align="center"><strong>Guarded iCloud Photos to NAS mirroring for a local-first photo library</strong></p>
<p align="center">Planning Before Mutation · SHA-First Matching · Automation With Manual Apply</p>

<table>
  <tr>
    <td width="33%" valign="top">
      <strong>Primary Use</strong><br/>
      Mirror <code>iCloud Photos</code> into a NAS library without turning the NAS into the catalog authority
    </td>
    <td width="33%" valign="top">
      <strong>Interface</strong><br/>
      Python CLI plus shell wrappers, with an optional <code>launchd</code> job for scheduled planning
    </td>
    <td width="33%" valign="top">
      <strong>Safety Model</strong><br/>
      <code>plan</code> can run automatically, <code>apply</code> stays explicit, and NAS deletions move into a reviewed holding area
    </td>
  </tr>
</table>

> Publicly, `icloud-photo-sync` is a local-first mirror tool for `iCloud Photos -> NAS`. Internally, it is a guarded two-step sync surface that separates planning from file mutations.

## Product Position

Use this repository when `iCloud Photos` is your only source of truth, `NAS` is the mirror that should follow it, and you want repeatable file-level synchronization instead of ad hoc export-and-copy routines.

This repository is intentionally narrower than a generic photo manager:

- `iCloud Photos` is the authoritative library
- the NAS is the mirror target, not the daily editing surface
- `OneDrive` or similar tools can remain backup relays, but they do not decide what is current

## What It Helps You Do

- Build a `plan` from the current Photos library, NAS contents, and persisted sync state.
- Copy new or missing iCloud assets into the NAS mirror.
- Detect NAS-only items after they disappear from iCloud and move them into `/Volumes/home/Photos_DeletedFromICloud` instead of hard-deleting them.
- Keep all operational receipts under `/Volumes/home/Photos_SyncLogs/YYYY-MM-DD/<plan_id>/`.
- Run scheduled discovery without giving scheduled jobs permission to mutate the NAS directly.

## Quick Start

Run from the repository root:

```bash
python3 -m tools.icloud_photo_sync.cli plan
python3 -m tools.icloud_photo_sync.cli apply --plan-dir /Volumes/home/Photos_SyncLogs/YYYY-MM-DD/<plan_id>
```

Wrapper scripts are provided for the common path:

```bash
./scripts/run_plan.sh
./scripts/run_apply_latest.sh --plan-dir /Volumes/home/Photos_SyncLogs/YYYY-MM-DD/<plan_id>
./scripts/run_apply_latest.sh --latest
```

## Runtime Layout

Repository-tracked content stays small and stable:

- source code under `tools/icloud_photo_sync/`
- tests under `tests/`
- operational docs under `docs/`

Runtime state stays outside Git intent even when some paths live inside the repo working tree:

- state DB: `state/icloud-photo-sync/state.sqlite3`
- staging directory: `tmp/icloud_photo_sync_stage`
- sync logs: `/Volumes/home/Photos_SyncLogs`
- NAS deleted pool: `/Volumes/home/Photos_DeletedFromICloud`

## Automation Model

The recommended automation policy is intentionally asymmetric:

- automate `plan`
- keep `apply` manual
- review the generated plan or the latest plan directory before mutating the NAS

That keeps daily discovery cheap while preserving a hard gate before file copies and deletion moves.

## Current Boundaries

- The current implementation is built around macOS Photos library access and the bundled Swift bridge.
- Matching is strict and content-oriented; the workflow does not rely on fuzzy heuristics to collapse near-duplicates.
- NAS-side deletions are implemented as audited moves into a holding area, not immediate destructive removal.
- This repository is a sync tool, not a general DAM, cloud backend, or gallery UI.

## For Agents

Operate this repository through the CLI and wrapper scripts instead of re-implementing the sync logic.

Typical agent tasks:

- run `plan`
- inspect the generated receipts
- run `apply` for an explicitly selected plan directory
- install or audit the scheduled `plan` automation

## Documentation

- [Automation guide](docs/automation.md)
- [Authoritative workflow notes](docs/icloud-photo-authoritative-workflow.md)
- [Design spec](docs/specs/2026-04-09-icloud-photo-sync-design.md)
- [Implementation plan](docs/plans/2026-04-09-icloud-photo-sync.md)

The detailed docs are currently Chinese-first because the active operator surface is personal and local.

## Technical Validation

```bash
python3 -m pytest tests -q
```

# Manual Operations

Photo Steward is manual-only. It does not install, restore, or run a macOS
LaunchAgent or a Synology DSM schedule. The App and command-line wrappers call
the same deterministic CLI; neither surface infers approval.

## Operating contract

1. iCloud Photos is the unique source authority.
2. NAS and off-site storage are mirrors or backups.
3. A plan is immutable evidence, not authorization to mutate data.
4. Apply requires review and explicit approval of the exact plan directory.
5. Retention remains audit-only unless its exact candidate set is separately
   reviewed and approved.

No manual command should be placed in `launchd`, cron, DSM Task Scheduler, or a
generic job runner without a new user decision and a new safety review.

## Photo plan and apply

Use the App for the normal workflow. The equivalent CLI flow is:

```bash
photo-steward config validate
photo-steward preflight
photo-steward status --scope photo --format json
photo-steward plan-job
```

Read the emitted plan directory, `plan_summary.json`, and the action manifests.
Explain mirror count, quarantine count, unresolved count, bytes, and affected
resources. Do not apply when `unresolved_count` is non-zero.

After explicit approval of that exact directory:

```bash
photo-steward apply-job --plan-dir <exact-plan-directory>
photo-steward status --scope photo --format json
```

Completion requires a successful apply receipt and target-side readback.

The compatibility wrapper accepts an exact plan directory:

```bash
./scripts/run_apply_latest.sh --plan-dir <exact-plan-directory>
```

Do not use an automatically selected latest plan as approval evidence.

## Optional manual checks

These wrappers remain available for owner-triggered maintenance:

```bash
./scripts/run_plan.sh
./scripts/run_todo_plan.sh
./scripts/run_deleted_pool_retention.sh
./scripts/run_onedrive_backup.sh
```

`run_deleted_pool_retention.sh` is a dry-run audit. It does not authorize
retention deletion. `run_onedrive_backup.sh` follows the configured backup
adapter and must be followed by its receipt and destination readback.

## Synology worker

The NAS worker is a manual storage-maintenance entry point. Installing it also
runs a dry-run, but does not create a DSM schedule:

```bash
PHOTO_STEWARD_NAS_HOST=<ssh-destination> \
  ./scripts/nas/install_synology_worker.sh
```

The installer prints the remote worker path. Run it manually only when NAS
maintenance is requested. The worker never uses `rsync --delete`. Retention is
still audit-only unless `--apply-retention` is explicitly supplied after review.

## Legacy schedule retirement

Version 0.4.1 and later run this idempotent cleanup during App startup:

```bash
./scripts/retire_launchd_agents.sh
```

It unloads and removes the known legacy labels:

- `com.photosteward.weekly`
- `com.photosteward.nas-maintenance.weekly`
- `com.photosteward.plan.daily`
- `com.photosteward.todo.daily`
- `com.photosteward.deleted-pool.daily`
- `com.photosteward.onedrive.daily`

It also removes the older `*.icloud-photo-sync.*.plist` family. The cleanup
does not touch photos, plans, receipts, logs, configuration, or NAS data.

Verify the local schedule surface with:

```bash
find "$HOME/Library/LaunchAgents" -maxdepth 1 \
  \( -name 'com.photosteward*.plist' -o -name '*.icloud-photo-sync.*.plist' \) \
  -print
launchctl print gui/$(id -u)/com.photosteward.weekly
```

The first command should print nothing. The second should report that the
service cannot be found.

For an existing DSM task, export its exact definition before disabling or
removing it through Synology's owner-supported Task Scheduler surface. Do not
run the task while changing its schedule.

## Failure handling

- Missing NAS mount or unexpected filesystem: stop before plan or apply.
- Photos permission failure: restore App permission, then retry manually.
- Plan generation failure: preserve the previous pending plan and report the
  new failure; do not apply the older plan without reviewing it again.
- Unknown apply result: read the exact receipt and target state before any
  retry.
- NAS worker failure: preserve its receipt and diagnose the first failed stage;
  do not convert it into a scheduled retry loop.

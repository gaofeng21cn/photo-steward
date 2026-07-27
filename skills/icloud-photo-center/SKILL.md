---
name: icloud-photo-center
description: "Use for the iCloud-centered photo hub: inspect current sync health, explain NAS and iCloud differences, create or review guarded plans, and execute an explicitly approved plan through the installed icloud-photo-sync CLI. Never replace deterministic manifest, SHA-256, guard, receipt, or quarantine checks with visual guesses or ad hoc file copying."
---

# iCloud Photo Center

Use this skill when the user asks about photo synchronization, iCloud Photos
as the authority, NAS mirror status, missing photos, date relocation, the
deleted/quarantine pool, OneDrive photo backup, or the photo center service.

## Product boundary

- iCloud Photos is authoritative.
- NAS `/Volumes/home/Photos` is a mirror.
- `/Volumes/home/Photos_DeletedFromICloud` is a quarantine pool, not an
  immediate hard-delete target.
- OneDrive is an off-site backup and does not decide which file is current.
- The CLI and receipts own data correctness. AI explains, groups, and reviews;
  it does not invent identity or override guards.

## Standard workflow

1. Read current health before making a claim:

   ```bash
   icloud-photo-sync preflight
   icloud-photo-sync status --scope photo --format json
   ```

2. For a current difference, run a new plan unless the user explicitly names
   an existing plan directory. Read `plan_summary.json`, then inspect the
   relevant action manifests. A plan is not an apply.

3. Explain counts and categories in plain language:
   - `mirror_count`: iCloud resources missing from NAS and proposed for export.
   - `delete_count`: NAS files absent from the current iCloud manifest and
     proposed for quarantine.
   - `unresolved_count`: ambiguity or scan failure; any non-zero value blocks
     apply.
   - date relocation is represented by a mirror action for the new path and a
     guarded quarantine action for the old path.

4. Before apply, require an explicit user approval for the exact plan
   directory. Do not infer approval from an earlier plan, a prior conversation,
   or a general request to “keep it synced”.

5. Execute only through the CLI:

   ```bash
   icloud-photo-sync apply-job --plan-dir /Volumes/home/Photos_SyncLogs/YYYY-MM-DD/<plan_id>
   ```

6. Read `apply_receipt.json` and `icloud-photo-sync status --scope photo
   --format json`. Completion requires `status=success`, zero guard failures,
   and target-side readback. `partial` or failed results remain unfinished.

## Review rules

- Do not use filename, filesystem timestamps, or visual similarity as identity.
  Use the plan's resource key, bytes, SHA-256, and state token.
- Do not apply a plan with `unresolved_count > 0`.
- Do not hard-delete NAS-only content. If the user approves deletion, the
  implementation still moves it to the dated quarantine pool.
- For a large mirror plan, summarize total bytes and month/type distribution;
  the user normally reviews the policy and outliers, not every file.
- For a quarantine plan, list every item with its path, size, SHA-256, and why
  it is absent from iCloud. Ask whether the user intended the iCloud deletion.
- If the mount is absent or its source/filesystem do not match the preflight
  contract, stop the operation and report the actual mount error.

## Related surfaces

- `icloud-photo-sync status --scope photo --format markdown` is the compact
  human overview.
- `icloud-photo-sync status --scope photo --format json` is the machine
  contract used by the menu bar app.
- `scripts/install_launchd_agents.sh` installs the default photo automation.
- `scripts/install_launchd_todo_agent.sh` is opt-in and separate from the
  photo-center health surface.

Never create a second sync implementation inside a response, skill script, or
GUI. Extend the repository CLI only when the deterministic contract itself
needs a change.

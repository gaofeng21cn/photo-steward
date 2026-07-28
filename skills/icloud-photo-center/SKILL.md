---
name: icloud-photo-center
description: "Use for the iCloud-centered Photo Steward service: inspect sync health, explain configured mirror differences, create or review guarded plans, and execute only an explicitly approved exact plan through icloud-photo-sync. Never replace deterministic manifests, SHA-256, guards, receipts, or quarantine checks with visual guesses or ad hoc file copying."
---

# iCloud Photo Center

Use this skill for Photo Steward questions about iCloud Photos as the authority,
NAS mirror health, missing photos, date relocation, quarantine, or off-site
backup. The Skill name is retained for compatibility; the public-facing working
name is Photo Steward.

## Boundary

- iCloud Photos is the unique authority.
- The configured `mirror.photos_root` is a mirror, not a source.
- `mirror.quarantine_root` is a reviewable quarantine pool, not an immediate
  hard-delete target.
- The CLI and receipts own data correctness. AI explains and reviews; it does
  not invent identity or override a guard.

## First use

```bash
icloud-photo-sync config path
icloud-photo-sync config validate
icloud-photo-sync preflight
```

If the private file is absent, run `icloud-photo-sync config init`. Ask the
user for their local Photos library and mounted NAS locations, then have them
review the completed TOML. Never write passwords, tokens, photo names, or
personal paths into a response artifact or Git file.

`config validate` checks schema and policy. `preflight` checks the real mount.
If either fails, explain the exact failure and do not generate or apply a plan.

## Standard workflow

1. Read `preflight` and `status --scope photo --format json` before claiming
   health:

   ```bash
   icloud-photo-sync preflight
   icloud-photo-sync status --scope photo --format json
   ```
2. Create a new plan unless the user explicitly selects an existing directory.
   Read `plan_summary.json` and the relevant manifests. A plan is not apply.
3. Explain `mirror_count`, `delete_count`, `unresolved_count`, total bytes, and
   any quarantine effect in plain language.
4. Require explicit approval for that exact plan directory. Never infer it from
   a general request or a prior conversation.
5. Execute only `icloud-photo-sync apply-job --plan-dir <exact-plan-dir>`.
6. Read `apply_receipt.json` and fresh JSON status. Completion requires
   `status=success`, zero guard failures, and target-side readback.

## Review rules

- Use the plan resource key, bytes, SHA-256, and state token for identity; not
  filenames, timestamps, or visual similarity.
- Do not apply a plan with `unresolved_count > 0`.
- Do not hard-delete mirror-only content. Approved removal still moves it into
  the configured dated quarantine pool.
- For large mirror plans, summarize total bytes and month/type distribution.
- For quarantine plans, list every item with path, size, SHA-256, and source
  absence reason, then ask whether the iCloud removal was intentional.
- If the configured mount fails preflight, stop and report the actual mount
  condition.

Never create a second sync implementation inside a response, Skill script, or
GUI. Extend the CLI only when the deterministic contract needs to change.

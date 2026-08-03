# Architecture

Photo Steward is a local-first photo mirror coordinator for macOS. It exposes
one deterministic execution engine through three user-facing interfaces. The
split makes responsibility clear; it does not duplicate synchronization logic.

| Layer | Owns | Does not own |
| --- | --- | --- |
| CLI | Config parsing, manifests, identity matching, plans, guards, apply, receipts, status | Conversational interpretation or GUI state |
| Codex Skill | Health explanation, plan review, explicit approval workflow | File copying, matching rules, safety bypasses |
| macOS console | Status, progress, plan review, confirmation | Direct filesystem mutation or a second sync engine |
| Mac orchestrator | Weekly Photos-dependent planning and business-status aggregation | Apply or permanent deletion |
| NAS worker | Serialized NAS backup and retention audit | Source authority or Photos.framework work |

All interfaces call `photo-steward`. The legacy `icloud-photo-sync` command is
an equivalent compatibility alias. Its private configuration is the only
location for user-specific paths. This keeps common code reusable and keeps
Photos libraries, NAS topology, manifests, receipts, and state private.

## Source and mirror contract

```text
iCloud Photos / local Photos library  ->  authoritative source
NAS                                 ->  guarded mirror and quarantine
Off-site backup                     ->  backup of the NAS mirror
```

No operation derives source truth from NAS contents. A mirror-only file is
quarantined after review instead of hard-deleted. A changed capture date is an
export to the correct path plus a guarded quarantine move from the old path.

## Control and execution flow

1. `preflight` validates the configured external mount, filesystem type, and
   read/write capability. A local directory with the same name is rejected.
2. `plan` or `plan-job` writes an immutable plan directory with a summary and
   action manifests.
3. A user or Agent reviews the exact plan. Any unresolved item blocks apply.
4. `apply` or `apply-job` validates bindings and guard conditions, then makes
   the proposed mirror and quarantine changes.
5. A receipt and target-side readback record success or failure.

The plan/apply distinction is deliberate. Weekly discovery can be scheduled;
the mutation decision remains explicit.

## Scheduling boundary

The Mac owns work that requires the local Photos library and Photos.framework.
`com.photosteward.weekly` runs the photo plan and optional ToDo plan in order,
continues after a child-process failure, and writes one scheduler receipt that
separates process exit from business state such as `review_ready` or `blocked`.

NAS maintenance is a separate serial flow: off-site backup runs first, then
quarantine retention is audited. The NAS worker never uses `rsync --delete` and
retention remains audit-only unless `--apply-retention` is explicitly supplied.
The Mac keeps the same safe fallback until a verified handoff receipt proves
that DSM Task Scheduler and the required Cloud Sync deletion semantics are in
force. A deployed worker or dry-run receipt alone is not a handoff.

## Configuration and distribution boundary

The default private config is
`~/Library/Application Support/Photo Steward/config.toml`; it contains paths
and policy but no credentials. Runtime state, caches, plans, receipts, and logs
stay outside Git. See [`configuration.md`](./configuration.md).

The integrated installer is the normal distribution path: a versioned,
notarized App carries the runtime, CLI, Photos bridge, and Codex Skill, then
installs them into user-owned locations on first launch. Checkout-linked
installers remain available only for development and testing. Current
`com.photosteward.*` LaunchAgent labels are compatibility identifiers, not the
future product namespace.

## Non-goals

- Reverse sync from NAS to iCloud Photos.
- Automatic apply from a scheduled job.
- Permanent deletion during ordinary plan apply.
- Visual similarity, file names, or filesystem times as photo identity.
- Passwords, cloud tokens, or certificates in Git or `config.toml`.

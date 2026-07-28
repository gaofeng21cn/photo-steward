# Architecture

Photo Steward is a local-first photo mirror coordinator for macOS. It exposes
one deterministic execution engine through three user-facing interfaces. The
split makes responsibility clear; it does not duplicate synchronization logic.

| Layer | Owns | Does not own |
| --- | --- | --- |
| CLI | Config parsing, manifests, identity matching, plans, guards, apply, receipts, status | Conversational interpretation or GUI state |
| Codex Skill | Health explanation, plan review, explicit approval workflow | File copying, matching rules, safety bypasses |
| macOS console | Status, progress, plan review, confirmation | Direct filesystem mutation or a second sync engine |
| `launchd` wrappers | Scheduling, retries, notifications, stable process context | NAS paths, runtime paths, or TOML parsing |

All interfaces call `icloud-photo-sync`. Its private configuration is the only
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

The plan/apply distinction is deliberate. Daily discovery can be scheduled;
the mutation decision remains explicit.

## Configuration and distribution boundary

The default private config is
`~/Library/Application Support/Photo Steward/config.toml`; it contains paths
and policy but no credentials. Runtime state, caches, plans, receipts, and logs
stay outside Git. See [`configuration.md`](./configuration.md).

The current installer is an Alpha development installer: it links a checkout
into `~/.local/bin` and the Codex skills directory. A public release must use
versioned packages and a notarized app. Current `com.photosteward.*` LaunchAgent
labels are compatibility identifiers, not the future product namespace.

## Non-goals

- Reverse sync from NAS to iCloud Photos.
- Automatic apply from a scheduled job.
- Permanent deletion during ordinary plan apply.
- Visual similarity, file names, or filesystem times as photo identity.
- Passwords, cloud tokens, or certificates in Git or `config.toml`.

# Photo Steward installation management

Photo Steward is one Agent-native OPL MiniApp. `photo-steward` is its stable
Package identity. The desktop console, command-line interface, local Skill and
shared MCP review view call the same photo owner. A Codex plugin supplies an
integration entry point; it does not create another photo store or sync engine.

## Installation and activation

| Installation | Default location | Lifecycle |
| --- | --- | --- |
| Published desktop App | `~/Applications/Photo Steward.app` | Install, activate, exact-release update, uninstall |
| Developer desktop build | `~/Applications/Photo Steward Development/Photo Steward.app` | Built by the developer, activate, remove the build |
| Connected source checkout | Explicitly selected checkout | Connect, activate, unlink; the developer maintains source and dependencies |
| Codex integration | Codex's native plugin location | Managed by the configured Codex carrier |

CLI and Skill files are entry points into a selected installation, not additional
software products. The owner keeps the active runtime at
`~/Library/Application Support/Photo Steward/runtime/current`. Both command
names in `~/.local/bin` and the local Skill resolve through that pointer.
Explicit development connections are symlinks under `runtime/development/`;
they do not copy, move, reset or delete source code.

The desktop first-run setup delegates to the same installation owner. An
existing consistent selection is preserved. A legacy conflict between the
desktop runtime, CLI or Skill requires selecting an installation; opening a
window does not silently overwrite that choice.

## Agent and Framework entry point

```sh
photo-steward installation inspect --json
photo-steward installation inspect --check-update --json
python3 scripts/manage_installation.py --stdin
```

`inspect` is offline and reads installation evidence only. It does not require
photo configuration, request Photos access, mount a NAS or read business data.
`--check-update` explicitly reads GitHub's release metadata.

The Package declares the typed `opl_software_installation_cli` entry point and
includes its implementation in the content lock. Framework invokes that
verified relative entry point using `opl_software_installation.v1`; it does not
accept an arbitrary executable or UI-supplied command string. The request is a
JSON object containing `package_id`, `operation`, and the required action fields:

| Operation | Required fields |
| --- | --- |
| `inspect` | Optional `check_update: true` |
| `activate`, `unlink`, `uninstall` | `installation_id`, `expected_revision` |
| `update` | `installation_id`, `expected_revision`, exact `version` |
| `install` | Exact published `version` |
| `link` | Explicit `source` checkout path |

The owner returns `photo-steward.installations.v1`, with each installation's
stable path-bound ID, actual version, mode, location, entry points, revision and
supported actions. `active_installation_status` distinguishes `active`,
`inactive`, `unknown` and `conflict`; a missing selected ID is not silently
interpreted as “not installed”. These observations do not grant action authority.

Mutations re-read the exact installation and reject stale revisions. Published
installation verifies the release asset SHA-256, bundle identity, exact version,
Developer ID signature and Gatekeeper assessment before replacement. The user
must quit an affected running App. New files are staged on the destination
filesystem, with the previous bundle retained until replacement and activation
complete. Development updates stay with development tools.

## Data and shared resources

Uninstall removes the selected App and its active entry points. Unlink removes
the source connection and leaves the checkout intact. Both preserve private
configuration, Photos, NAS mirrors, plans, receipts and retained runtime copies.
They do not remove another installation or switch to an unselected one.

iCloud Photos remains the source of photo facts. OS Photos permissions, mounted
NAS access and existing credential providers own credentials. OPL shared
resources hold authorized references and configuration access; neither the
software catalog nor this installer creates a second photo library, credential
store or personal knowledge base.

The read-only shared MCP view and explicit reviewed-plan apply action remain in
`app-contribution-adapter.json`. Software lifecycle and photo plan execution are
separate actions, and installing or activating software never applies a photo
plan.

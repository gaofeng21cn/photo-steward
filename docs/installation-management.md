# Photo Steward installation management

Photo Steward is one Agent-native OPL MiniApp. `photo-steward` is its stable
Package identity. The desktop console, command-line interface, local Skill and
shared MCP review view call the same photo owner. The root `opl-package.json`
(`opl.package.v2`) declares the Framework integration entry point; it does not
create another photo store or sync engine.

## Installation, updates, and activation

| Installation | Default location | Lifecycle |
| --- | --- | --- |
| Published desktop App | `/Applications/Photo Steward.app` or `~/Applications/Photo Steward.app` | Signed & notarized DMG installation, native Sparkle 2 in-app updates, local CLI/Skill activation |
| Developer desktop build | `~/Applications/Photo Steward Development/Photo Steward.app` | Built by the developer via `scripts/install_menu_bar_app.sh`, local CLI/Skill activation |
| Connected source checkout | Explicitly selected checkout | Connect (`link`), activate, `unlink`; the developer maintains source and dependencies |
| OPL Package | OPL Framework (`opl pack`) managed installation | Managed via root `opl-package.json` (`opl.package.v2`) and optional host projections |

In-app updates for the macOS desktop App are owned exclusively by **Sparkle 2**
using Ed25519-signed `appcast.xml` feeds (`SUEnableAutomaticChecks = true`,
`SUAutomaticallyUpdate = false`) plus Developer ID signing and Apple
notarization. `installation.py` never downloads, extracts, verifies, or
replaces `.app` bundles.

CLI and Skill files are entry points into a selected installation, not
additional software products. The owner keeps the active runtime pointer at
`~/Library/Application Support/Photo Steward/runtime/current`. Both command
names in `~/.local/bin` and the local Skill resolve through that pointer.
Explicit development connections are symlinks under `runtime/development/`;
they do not copy, move, reset or delete source code.

The desktop first-run setup (`PhotoStewardRuntimeController.prepare()`)
delegates to the same lightweight activation owner. An existing consistent
selection is preserved. After a Sparkle in-app update replaces the `.app`
bundle, launching the updated App refreshes `runtime/current` to the updated
bundled runtime. A legacy conflict between the desktop runtime, CLI or Skill
requires explicit `activate`; opening a window does not silently overwrite that
choice.

## Agent and Framework entry point

```sh
photo-steward installation inspect --json
python3 scripts/manage_installation.py --stdin
```

`inspect` is strictly offline and reads local installation evidence only. It
does not require photo configuration, request Photos access, mount a NAS, hit
the network, or read business data.

The Package declares the typed `opl_software_installation_cli` entry point and
includes its implementation in the content lock. Framework invokes that
verified relative entry point using `opl_software_installation.v1`; it does not
accept an arbitrary executable or UI-supplied command string. The request is a
JSON object containing `package_id`, `operation`, and the required action
fields:

| Operation | Required fields |
| --- | --- |
| `inspect` | None |
| `activate`, `unlink` | `installation_id`, `expected_revision` |
| `link` | Explicit `source` checkout path |

The owner returns `photo-steward.installations.v1`, with each installation's
stable path-bound ID, actual version, mode, location, entry points, revision
and supported actions. `active_installation_status` distinguishes `active`,
`inactive`, `unknown` and `conflict`; a missing selected ID is not silently
interpreted as “not installed”. Mutations re-read the exact installation and
reject stale revisions.

## Data and shared resources

Unlinking a development checkout removes the source connection and leaves the
checkout intact. Removing the desktop App or switching active installations
preserves private configuration, Photos, NAS mirrors, plans, receipts and
retained runtime copies.

iCloud Photos remains the source of photo facts. OS Photos permissions, mounted
NAS access and existing credential providers own credentials. The read-only
shared MCP view and explicit reviewed-plan apply action are declared in
`opl-package.json` (`provides.contribution_handler` ->
`scripts/app_contribution.py` and `ui.declarative.views`). Software lifecycle and photo plan execution
are separate actions, and activating software never applies a photo plan.

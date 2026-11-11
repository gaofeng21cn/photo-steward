<p align="center"><strong>English</strong> | <a href="./README.zh-CN.md">中文</a></p>

<h1 align="center">Photo Steward</h1>

<p align="center"><strong>Guarded photo mirroring for macOS</strong></p>
<p align="center">iCloud Photos as authority · Review before mutation · Local data stays local</p>

> **Integrated installer.** Photo Steward is an independent macOS application
> published under [Apache-2.0](./LICENSE). Its release bundle is
> self-contained: it includes the sync runtime, Photos bridge, CLI, Codex
> Skill, and first-run setup.

Photo Steward coordinates a local macOS Photos library, iCloud Photos, and a
NAS mirror. It creates an auditable plan first, explains the difference, and
only changes the mirror after explicit approval. It is not a cloud gallery,
reverse-sync client, or general digital-asset manager.

`photo-steward` is the CLI and Codex Skill identifier. Existing scripts may
continue using the `icloud-photo-sync` CLI compatibility name.

## For Users

### What it protects

- **iCloud Photos remains the unique authority.** NAS and off-site copies are
  mirrors or backups; they never decide what is current in Photos.
- **Plans precede mutations.** A plan is created only when the user asks for
  one; background jobs do not scan or apply photo changes.
- **Mirror-only files go to quarantine.** They move into a dated, reviewable
  location instead of being hard-deleted.
- **A successful receipt is required.** Status changes only after the exact
  plan and guard checks complete successfully.

### Daily use

1. Open **Photo Steward** from the menu bar or ask Codex to inspect the
   photo center.
2. Refresh status and generate a plan when a new difference is expected.
3. Review counts, bytes, unresolved items, and proposed quarantine moves.
4. Approve the exact plan only when it matches your intent.
5. Read the resulting receipt and status summary.

The menu-bar app is a control console, not a second sync engine. It calls the
same deterministic CLI used by the Codex Skill.

### Privacy and data

The repository contains source, tests, public examples, and documentation. The
following remain on the user's Mac or NAS and must never be committed:

- Photos libraries, exported photo bytes, manifests, SHA-256 indexes, plans,
  receipts, SQLite state, and logs;
- NAS host names, mount paths, account names, and local absolute paths;
- cloud tokens, passwords, signing certificates, and developer credentials.

The private configuration lives at:

```text
~/Library/Application Support/Photo Steward/config.toml
```

It is created with mode `0600`. Use macOS Keychain, the NAS mount mechanism,
or the backup adapter's own credential store for secrets. The committed example
is [`config/photo-steward.example.toml`](./config/photo-steward.example.toml).

### Quick start

For normal use, download the latest
[Photo Steward release](https://github.com/gaofeng21cn/photo-steward/releases/latest),
unzip it, and move `Photo Steward.app` to `~/Applications`. Open the app and
choose:

1. the local Photos library;
2. the mounted NAS photo mirror directory.

The first-run wizard normally discovers the Photos library in `~/Pictures`;
you can change it if the Mac has more than one library. Select the mounted NAS
photo mirror directory, and the wizard installs the CLI at `~/.local/bin`,
installs the `photo-steward` Codex Skill under `~/.codex/skills`, writes the
private configuration, and requests Photos permission. It does not install
Mac or NAS schedules. No Python,
Swift, repository checkout, or manual
TOML editing is required.

The source checkout also contains developer-only installers:

```bash
./scripts/install_local.sh
./scripts/install_menu_bar_app.sh
```

They are for development and test workflows; they are not required by users of
the public App.

See [`docs/configuration.md`](./docs/configuration.md) for the schema and
migration guidance.

## How It Works

```text
iCloud Photos / local Photos library
              |
              v
    deterministic manifest and SHA-256 matching
              |
              v
          guarded plan
              |
              +--> review in Codex or the macOS console
              |
              v
       explicit apply and target-side readback
              |
              v
   NAS mirror, quarantine pool, and execution receipt
```

An unresolved resource blocks `apply`. A date correction is a relocation: the
new dated mirror item is created and the old location moves into quarantine
under the same guarded plan. Direct copying or visual duplicate guesses are
not valid substitutes.

## For Agents

The Codex Skill is the conversational entry point. The CLI owns configuration,
planning, safety checks, execution, and receipts. Never implement parallel sync
logic in a prompt, Skill script, or GUI.

```bash
photo-steward config validate
photo-steward preflight
photo-steward status --scope photo --format json
photo-steward plan-job
```

Before apply, the Agent must read `plan_summary.json` and relevant manifests,
explain `mirror_count`, `delete_count`, `unresolved_count`, bytes, and the
quarantine effect, then obtain approval for that exact plan directory. Execute
only:

```bash
photo-steward apply-job --plan-dir <exact-plan-dir>
```

Completion requires the resulting receipt plus a fresh JSON status readback.

The App installs the Skill locally; it does not silently install a remote Codex
plugin, grant Codex permissions, or upload any photo data. A new Codex task
will discover the Skill after installation.

Configuration precedence is: an operation-specific CLI option, global
`--config`, `PHOTO_STEWARD_CONFIG`, legacy `ICLOUD_PHOTO_SYNC_CONFIG`, the
private active-config pointer, then the default private path. `config activate`
updates the private pointer so the macOS app and manual CLI use the same
profile. The global option precedes the subcommand:

```bash
photo-steward --config /absolute/path/config.toml preflight
```

The macOS app reads the default private path. Manual CLI invocations can select
another profile with the global `--config` option.

### Manual operation

Photo Steward does not install or restore background schedules. Generate a plan
from the App, or run the same guarded path manually:

```bash
photo-steward preflight
photo-steward plan-job
```

Review the complete plan and explicitly apply its exact directory. The NAS
worker, OneDrive backup, and quarantine-retention audit also remain manual
entry points. See [`docs/automation.md`](./docs/automation.md).

## Software management

Photo Steward is one OPL MiniApp with desktop, CLI, Skill, and shared MCP review entry points. The software center manages the product; a Codex plugin is an integration entry point, not another photo application. Release and development installations can coexist, with one explicitly selected runtime for desktop, Agent, and CLI use.

`photo-steward installation inspect --json` reads versions, actual paths, activation, and supported operations without accessing Photos, NAS, or private configuration. Release updates use exact signed, notarized GitHub artifacts. Development connections can be activated or unlinked; updating software never edits a checkout. Uninstalling keeps photos, configuration, plans, and receipts. See [installation management](docs/installation-management.md).

## Architecture

- **CLI:** the testable command contract and only owner of sync semantics.
- **Codex Skill:** health inspection, plan explanation, and approval workflow.
- **macOS console:** status, progress, pending-plan review, and confirmation.

Manual wrappers and the App call the same CLI. See
[`docs/architecture.md`](./docs/architecture.md).

## Agent and shared review UI

The Package contribution reads owner-shaped JSON from `status --view` and
`pending-plan --view`. Pass `--plan-dir <directory>` to the latter to reopen
one exact plan after its pending pointer is cleared. `review-view --plan-dir`
returns the same projection; `plan-details --plan-dir` exposes its machine data.
The revision binds plan bytes and configured mirror/quarantine targets. Views
include the original operation and apply receipt rather than inferring success
from a closed dialog.

Shared actions call `apply-reviewed-plan --plan-dir <directory>
--plan-revision <revision> --request-id <request-id>`, which invokes the existing
`run_apply_job` owner. Its JSON response separates `success`, `partial`,
`rejected`, and `outcome_unknown`; progress goes to stderr. The contribution
adapter uses `--contribution` to return the standard OPL response envelope.
Plan directory, revision, and request identity are bound read-only form inputs.
Changed plan/target revisions are rejected before execution; the owner validates
and executes the same captured plan bytes, including binding updates. Existing
file state and content guards still run during apply. Receipts must match the
current plan identity and revision; an old target's success is a review conflict. Repeated calls and reopening
read the original operation/receipt, including a lost or interrupted response.
For partial or unknown outcomes, inspect the receipt and actual targets, then
create and review a fresh remaining-work plan; reopening never repeats apply.
These commands also work without a graphical host.

The native App and existing CLI commands remain the same sync owner. This
source change does not update an already installed native runtime; a carrier
using the new descriptor requires the matching CLI. Synthetic tests cover the
owner handoff and local-file mutation. Real Photos/NAS permissions, native App
installation, and cross-host UI acceptance are separate validation surfaces.

## Current Release

The latest published macOS release is identified by its GitHub release asset and bundle version. Its universal App
contains the CLI runtime, prebuilt Photos bridge, Codex Skill, first-run setup,
in-app NAS configuration, and reviewable photo plans. The public archive is
signed with Apple Developer ID, notarized, stapled, and accepted by Gatekeeper.
The source checkout remains useful for contributors, but a normal user should
install only the App from the latest release page.

iCloud and Photos describe the supported Apple integration; Photo Steward is
independent software and is not affiliated with Apple. The Apache-2.0 license
does not grant permission to use Apple, iCloud, or Photos trademarks.

Release validation is documented in [`docs/release.md`](./docs/release.md).

## License

Photo Steward is distributed under the [Apache License 2.0](./LICENSE).
Third-party components, if added later, must retain their own license and
attribution requirements.

## Verification

Package content-lock encoding is owned by Framework. The portable `scripts/_opl_package_content_lock.py` copy is generated with Framework's `scripts/materialize-python-support.mjs --module package_content_lock --target /path/to/photo-steward/scripts/_opl_package_content_lock.py`. Run `python3 scripts/materialize_package.py --check --framework-root /path/to/one-person-lab` to verify both the carrier and byte-for-byte helper parity.

```bash
python3 -m pytest tests -q
swift build --package-path app/PhotoCenterMenuBar -c release
zsh tests/test_menu_bar_app.sh
zsh tests/test_launchd_job.sh
zsh tests/test_install_local.sh
zsh tests/test_automation_common.sh
zsh tests/test_release_packaging.sh
zsh tests/test_runtime_bundle.sh
```

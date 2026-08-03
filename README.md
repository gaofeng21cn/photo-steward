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

`photo-steward` is the primary CLI and Codex Skill identifier. Existing
installations retain `icloud-photo-sync` (CLI) and `icloud-photo-center`
(Codex Skill) as compatibility aliases.

## For Users

### What it protects

- **iCloud Photos remains the unique authority.** NAS and off-site copies are
  mirrors or backups; they never decide what is current in Photos.
- **Plans precede mutations.** Scheduled work can discover differences, but it
  cannot silently apply a plan.
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
same deterministic CLI used by the Codex Skill and `launchd`.

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
private configuration, requests Photos permission, and installs the
weekly Mac orchestrator and guarded NAS-maintenance fallback. No Python,
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
updates the private pointer so the macOS app and LaunchAgents use the same
profile. The global option precedes the subcommand:

```bash
photo-steward --config /absolute/path/config.toml preflight
```

The macOS app reads the default private path. `launchd` records the selected
path explicitly in each generated plist and does not inherit terminal state.

### Automation

Install automation only after `config validate` and `preflight` pass:

```bash
./scripts/install_launchd_agents.sh
```

The Mac installs one weekly orchestrator at Sunday 03:15. It creates a photo
plan and, when configured, a ToDo plan; it never applies either plan. Until a
verified Synology handoff exists, a second Sunday 04:00 fallback serializes the
NAS-to-OneDrive backup and a quarantine-retention audit. Retention is dry-run
by default. Logs belong in `~/Library/Logs/Photo Steward/`; generated
LaunchAgents contain a config path but no credentials.

Synology deployment is intentionally guarded. The NAS worker can be installed
and dry-run over SSH, but the Mac fallback is disabled only after a local
handoff receipt confirms that DSM Task Scheduler is installed and Cloud Sync
is upload-only without deleting cloud objects when the NAS source disappears.
See [`docs/automation.md`](./docs/automation.md).

## Architecture

- **CLI:** the testable command contract and only owner of sync semantics.
- **Codex Skill:** health inspection, plan explanation, and approval workflow.
- **macOS console:** status, progress, pending-plan review, and confirmation.

`launchd` invokes wrappers that call the same CLI instead of routing through
the app. See [`docs/architecture.md`](./docs/architecture.md).

## Release Readiness

Version `0.4.0` is the integrated-installer release candidate. Its universal
App contains the runtime required by the CLI, the prebuilt Photos bridge, the
Codex Skill, and the first-run setup flow. A public download is published only
after the App is notarized and accepted by Gatekeeper. The source checkout
remains useful for contributors, but a normal user should install only the App.

iCloud and Photos describe the supported Apple integration; Photo Steward is
independent software and is not affiliated with Apple. The Apache-2.0 license
does not grant permission to use Apple, iCloud, or Photos trademarks.

Release validation is documented in [`docs/release.md`](./docs/release.md).

## License

Photo Steward is distributed under the [Apache License 2.0](./LICENSE).
Third-party components, if added later, must retain their own license and
attribution requirements.

## Verification

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

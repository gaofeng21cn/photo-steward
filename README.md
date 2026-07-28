<p align="center"><strong>English</strong> | <a href="./README.zh-CN.md">中文</a></p>

<h1 align="center">Photo Steward</h1>

<p align="center"><strong>Guarded photo mirroring for macOS</strong></p>
<p align="center">iCloud Photos as authority · Review before mutation · Local data stays local</p>

> **Alpha status.** Photo Steward is reusable as a developer-operated local
> service, but it is not yet a packaged public release. The source currently
> is licensed under [Apache-2.0](./LICENSE), but the project still lacks a
> public source distribution, notarized installer, and final trademark
> clearance.

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

The current installer links this checkout. It is suitable for technical Alpha
evaluation, not public software distribution.

```bash
./scripts/install_local.sh
photo-steward config path
# Edit the private file printed above.
photo-steward config validate
photo-steward preflight
photo-steward status --scope photo --format json
```

Install the optional macOS console after configuration validates:

```bash
./scripts/install_menu_bar_app.sh
open "$HOME/Applications/Photo Steward.app"
```

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

The default schedule creates a plan, runs quarantine retention, and can run an
off-site backup. It does **not** apply a photo plan. Logs belong in
`~/Library/Logs/Photo Steward/`; generated LaunchAgents contain a config path
but no credentials. Folder and ToDo adapters are optional advanced extensions.

## Architecture

- **CLI:** the testable command contract and only owner of sync semantics.
- **Codex Skill:** health inspection, plan explanation, and approval workflow.
- **macOS console:** status, progress, pending-plan review, and confirmation.

`launchd` invokes wrappers that call the same CLI instead of routing through
the app. See [`docs/architecture.md`](./docs/architecture.md).

## Release Readiness

This Alpha can be shared with a trusted technical evaluator who creates their
own private configuration and understands the checkout-linked installation.
A public release still requires:

- a public source repository and release artifacts built from a fresh clone;
- a decision about whether to rewrite or retain the existing Git author history;
- a versioned installer instead of checkout symlinks;
- a notarized universal macOS app and end-user permission guidance;
- final product-name and trademark clearance;
- an external-user installation and recovery test.

The source is licensed under Apache-2.0, but the repository is currently private
and the project is not yet a generally available software release. iCloud and
Photos only describe the supported Apple integration; Photo Steward is
independent software and is not affiliated with Apple.

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
```

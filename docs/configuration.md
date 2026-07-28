# Configuration

Photo Steward keeps every machine-specific path in one private TOML file. The
CLI owns schema parsing; the Codex Skill, macOS console, wrappers, and
`launchd` all call the CLI rather than interpreting paths independently.

## Location and precedence

The default private configuration is:

```text
~/Library/Application Support/Photo Steward/config.toml
```

Locate, initialize, validate, and then verify it with:

```bash
icloud-photo-sync config path
icloud-photo-sync config init
icloud-photo-sync config validate
icloud-photo-sync config activate
icloud-photo-sync preflight
```

`config init` writes a mode `0600` template and refuses to overwrite an
existing file without `--force`. `config validate` checks TOML syntax, required
fields, path relationships, and the no-secrets policy. `preflight` separately
checks the real mounted filesystem.

The precedence order is:

1. An operation-specific CLI option, such as `--nas-root`.
2. Global `--config /absolute/path/config.toml`.
3. `PHOTO_STEWARD_CONFIG`.
4. Legacy `ICLOUD_PHOTO_SYNC_CONFIG`, retained for existing installations.
5. The private active-config pointer at
   `~/Library/Application Support/Photo Steward/active-config-path`.
6. The default private path.

The global option comes before the subcommand:

```bash
icloud-photo-sync --config /absolute/path/config.toml preflight
```

`config activate` writes the selected path to the private pointer. The macOS
console resolves that pointer, while `launchd` records the same selected path
in each generated plist. This prevents a custom CLI profile, the App, and
scheduled work from targeting different libraries or NAS mounts.

## Schema

Begin with [`../config/photo-steward.example.toml`](../config/photo-steward.example.toml):

```toml
schema_version = 1

[photos]
library_path = "~/Pictures/Photos Library.photoslibrary"
# Optional. Default: <library_path>/database/Photos.sqlite
# database_path = "~/Pictures/Photos Library.photoslibrary/database/Photos.sqlite"

[mirror]
mount_root = "/Volumes/your-nas"
photos_root = "/Volumes/your-nas/Photos"
quarantine_root = "/Volumes/your-nas/PhotoSteward_Quarantine"
receipts_root = "/Volumes/your-nas/PhotoSteward_Receipts"
expected_filesystem = "smbfs"

[runtime]
state_dir = "~/Library/Application Support/Photo Steward/state"
cache_dir = "~/Library/Caches/Photo Steward"

# Optional off-site backup:
# [backup]
# onedrive_root = "~/OneDrive/Backup/PhotoSteward"
```

| Field | Meaning |
| --- | --- |
| `photos.library_path` | Local macOS Photos library. |
| `photos.database_path` | Optional Photos SQLite path. |
| `mirror.mount_root` | NAS mount point checked by the mount contract. |
| `mirror.photos_root` | NAS destination for mirrored photo resources. |
| `mirror.quarantine_root` | Mirror-only resources move here instead of being hard-deleted. |
| `mirror.receipts_root` | Plan manifests and execution receipts below the NAS mount. |
| `mirror.expected_filesystem` | Expected filesystem, normally `smbfs` on macOS. |
| `runtime.state_dir` | Private SQLite state and machine-readable status. |
| `runtime.cache_dir` | Private staging/cache directory. |
| `runtime.state_db` | Optional SQLite override for a pre-existing state layout. |
| `runtime.status_dir` | Optional status directory override for a pre-existing dashboard. |
| `runtime.stage_dir` | Optional staging directory override. |
| `backup.onedrive_root` | Optional off-site backup destination. Omit `[backup]` when unused. |

The optional `[extensions.todo]` table accepts `source_root`, `target_root`,
and `review_root`. It is intentionally excluded from the normal photo setup.

## Security and migration

The schema accepts only the fields documented above and rejects unknown keys,
including common credential variants such as `nas_password`, `access_token`, or
`client_secret`. Keep NAS credentials in the mount/keychain layer and backup
credentials in the adapter's own store. Generated LaunchAgent files contain the
configuration path only, never credentials or config content.

For an existing deployment, keep the current runtime paths in the first private
configuration so historical dashboard status and receipts remain visible. Move
state into the documented `runtime.state_dir` only as a separate,
non-destructive migration. Reinstall local links and automation after the new
configuration validates:

```bash
./scripts/install_local.sh
./scripts/install_launchd_agents.sh
```

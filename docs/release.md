# Release

This document separates a public source release from a notarized macOS app
release. Photo Steward `v0.3.0` is the first public notarized macOS App
release; the source and the App remain Alpha.

## Local Validation

Run from a clean checkout:

```bash
python3 -m pytest tests -q
swift build --package-path app/PhotoCenterMenuBar -c release
zsh scripts/verify_fresh_clone.sh <clone-source>
```

The fresh-clone script must run against the exact source revision intended for
release. It checks the license, public examples, ignored runtime boundaries,
privacy markers, Python tests, and Swift build.

## Signed Artifact

The release packager builds arm64 and x86_64 binaries, combines them into one
universal app, includes the Photo Steward icon, and signs the app with
Developer ID and the hardened runtime:

```bash
scripts/package_release.sh
```

This produces a signed but unnotarized validation artifact. It is not a public
distribution artifact.

## Published App

The current public App release is
[Photo Steward 0.3.0](https://github.com/gaofeng21cn/photo-steward/releases/tag/v0.3.0).
Its universal ZIP passed `codesign`, `stapler validate`, and Gatekeeper after
stapling. The published asset is:

```text
Photo-Steward-0.3.0-macOS-universal.zip
sha256: bdae28c4b9a26e7f7c20c2e07ee7db23e153b31502e920ac83b99f6a23e21396
```

The release is notarized, but the checkout-linked installer remains a
development and technical-evaluation path.

## Notarization

Notarization requires an Apple notarization credential stored in the login
keychain. The credential is never committed to Git or written to a config file.
Create it once using an app-specific password or an App Store Connect API key:

```bash
xcrun notarytool store-credentials PhotoStewardNotary \
  --apple-id <apple-id> \
  --team-id <team-id> \
  --password <app-specific-password>
```

Then package, submit, staple, and verify:

```bash
PHOTO_STEWARD_NOTARY_PROFILE=PhotoStewardNotary \
  scripts/package_release.sh --notarize
```

The terminal artifact must pass all of:

```bash
codesign --verify --deep --strict "dist/Photo Steward.app"
xcrun stapler validate "dist/Photo Steward.app"
spctl --assess --type execute --verbose=4 "dist/Photo Steward.app"
```

`spctl` returning `Unnotarized Developer ID` means the signature is valid but
the notarization ticket is absent. That result is expected for the validation
path and is a release failure for the public app path.

## Public Source

Before treating a source revision as a public release:

1. Push the exact intended `main` commit.
2. Run `scripts/verify_fresh_clone.sh` from a fresh clone.
3. Confirm that only generic examples, not private runtime data, appear in the
   tree.
4. Confirm that the README says whether the app is source-only Alpha or a
   notarized distribution.
5. If the repository is not public yet, make the visibility change and read
   back the public repository and license.

The Apache-2.0 license does not grant permission to use Apple, iCloud, Photos,
or Photo Steward trademarks.

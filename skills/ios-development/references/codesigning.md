# Code signing & provisioning

A condensed cheat sheet for the device-deploy errors that bite most often.

## The mental model

To install on a physical device, every `.app` needs:

1. A **signing identity** (a private key + Apple-issued certificate stored
   in the Keychain).
2. A **provisioning profile** that:
   - is signed by Apple,
   - lists the bundle id (or a wildcard that matches it),
   - lists the device's UDID (development profiles), and
   - is signed by the same team as the certificate.

`xcodebuild` with `CODE_SIGN_STYLE=Automatic` + a `DEVELOPMENT_TEAM` will
do the right thing nine times out of ten. `ios-localdeploy` sets both.

## Common errors

### `No profiles for 'com.example.app' were found`

The bundle id is not covered by any installed profile.

- Pick a bundle id you actually own (your team's reverse-DNS prefix).
- Open Xcode once, sign in to Apple ID under
  *Settings → Accounts*, and let Xcode generate a free profile. From then
  on `xcodebuild` can reuse it.

### `Code Signing Identity '…' does not match any valid, non-expired … certificate`

Your certificate expired or was revoked. Download a fresh one via
*Xcode → Settings → Accounts → Manage Certificates → +*. The new cert is
written to the login keychain automatically.

### `errSecInternalComponent` during `codesign`

The keychain is locked or the codesign tool can't reach it. On a remote
build host, unlock the keychain explicitly:

```bash
security unlock-keychain -p "$KEYCHAIN_PASSWORD" ~/Library/Keychains/login.keychain-db
```

### `App installation failed: Could not write to the device`

Usually caused by one of:

- The device is locked. Unlock and retry.
- `Settings → General → VPN & Device Management` has a pending trust prompt
  for the developer. Approve it once.
- The device storage is full. Free space and retry.

## When all else fails

Run with `OTHER_CODE_SIGN_FLAGS=-v` plus `xcodebuild ... -showBuildSettings
| grep -i sign` to see exactly which identity, profile, and entitlements
were chosen, then compare against `security find-identity -v -p
codesigning` and the profiles in `~/Library/MobileDevice/Provisioning\
Profiles/`.

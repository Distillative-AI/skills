# xcodebuild cheatsheet

## Discovery

| Goal | Command |
| --- | --- |
| List schemes in a project | `xcodebuild -project MyApp.xcodeproj -list` |
| List all build settings | `xcodebuild -scheme MyApp -showBuildSettings` |
| Find the produced `.app` | `xcodebuild -scheme MyApp -showBuildSettings -json \| jq '.[0].buildSettings.TARGET_BUILD_DIR'` |
| List simulators | `xcrun simctl list -j devices available` |
| List paired devices | `xcrun devicectl list devices` |

## Build / test / clean

| Goal | Command |
| --- | --- |
| Build for a sim, no signing | `xcodebuild -scheme MyApp -destination 'platform=iOS Simulator,name=iPhone 15' CODE_SIGNING_ALLOWED=NO build` |
| Build for device | `xcodebuild -scheme MyApp -destination 'generic/platform=iOS' DEVELOPMENT_TEAM=ABCDE12345 CODE_SIGN_STYLE=Automatic build` |
| Run unit tests | `xcodebuild -scheme MyApp -destination 'platform=iOS Simulator,name=iPhone 15' test` |
| Run a single test | `xcodebuild ... test -only-testing:MyAppTests/FeedViewModelTests/test_load` |
| Clean derived data | `rm -rf ~/Library/Developer/Xcode/DerivedData/MyApp-*` |

## Useful flags

- `-quiet` — silence everything except warnings/errors.
- `-derivedDataPath PATH` — pin DerivedData to your project (handy for CI).
- `-resultBundlePath PATH.xcresult` — capture a bundle for `xcrun xcresulttool`.
- `-allowProvisioningUpdates` — let Xcode fix expired free profiles.
- `OTHER_SWIFT_FLAGS="-warnings-as-errors"` — fail on warnings.

# Running Ralph VC on your iPhone

> **Heads-up:** I (the assistant authoring this skill) cannot push the app to
> your phone for you — there's no Mac, Xcode, or paired device in my sandbox.
> What this doc gives you is a **one-command path** that does the whole thing
> on your Mac.

## What you need (one-time setup)

1. **A Mac with Xcode 15+ installed.** Open Xcode once after install so it
   accepts the licence agreement and downloads the iOS platform support.
2. **An Apple Developer account.** A free Apple ID works for personal
   testing on a single device. Find your **Team ID** at
   <https://developer.apple.com/account> → *Membership*.
3. **An Anthropic API key.** Get one at <https://console.anthropic.com>.
4. **An iPhone.** Plug it into the Mac with a USB cable. The first time you
   connect, the iPhone will ask you to *Trust this computer* — accept.
5. **The two skills installed side-by-side**, e.g. via the marketplace plugin:

       /plugin install ios-development@anthropic-agent-skills
       /plugin install ralph-vc-ios@anthropic-agent-skills

   …or by cloning this repo so `skills/ios-development` and
   `skills/ralph-vc-ios` are siblings.

## The one-command flow

```bash
# from the ralph-vc-ios skill directory
export ANTHROPIC_API_KEY=sk-ant-...
./setup.sh --device --team-id ABCDE12345
```

That script:

1. Verifies you're on macOS, that Xcode is installed, and that
   [`xcodegen`](https://github.com/yonaskolb/XcodeGen) is available
   (it `brew install`s it on first run).
2. Generates `ios-app/RalphVC.xcodeproj` from the version-controlled
   `ios-app/project.yml`.
3. Starts the localhost orchestrator server (`server/server.py`) in the
   background on `0.0.0.0:7878`. It mints an ephemeral
   `RALPHVC_BEARER` token if you didn't set one.
4. Calls `python ../ios-development/app/deploy.py --target device --team-id …`
   which runs `xcodebuild build` with automatic signing, locates the
   produced `RalphVC.app`, and installs + launches it on your iPhone via
   `xcrun devicectl` (falling back to `ios-deploy` if your Xcode is older).

When it's done you'll see a banner like:

```
done.
- The Ralph VC app is now running on your device.
- The local server is listening on http://0.0.0.0:7878 (PID 12345).
- On the iPhone, point Settings → Endpoint at http://<your-mac-ip>:7878
  and paste your bearer token: 8a4d…
- Tap the mic and start vibe-coding.
```

## Iterating on the simulator first

Skip the team-id and the cable:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
./setup.sh --simulator
```

Same flow, but builds for the iOS Simulator (no signing, no device).

## What to do on the iPhone

1. The Ralph VC app launches automatically.
2. iOS will prompt for **Microphone** and **Speech Recognition** permission
   the first time you tap the mic — accept both.
3. Open the in-app Settings (gear icon) and:
   - **Endpoint:** `http://<your-mac-ip>:7878` (the script prints your
     Mac's IP; or grab it from System Settings → Wi-Fi → ⓘ).
   - **Bearer token:** the value the script printed (it's also in the
     terminal as `RALPHVC_BEARER`).
4. Tap **Save**. The app stores the token in the iPhone's Keychain.
5. Tap the mic, say *"What's the latest in Swift 6 strict concurrency?"*,
   and Ralph will reply via Sonnet 4.6 — both as text in the chat and
   spoken aloud through the **Ralph voice** if you have it installed
   (Settings → Accessibility → Spoken Content → Voices → English → Ralph).

## Updating after a code change

```bash
./setup.sh --device --team-id ABCDE12345
```

Re-running the script regenerates the project (xcodegen is idempotent),
rebuilds, and re-installs. If the server is already running it'll
warn-but-continue — pass `--no-server` to skip the server start.

## Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| `xcrun: error: tool 'xcodebuild' requires Xcode` | Command-line tools only | Open Xcode once and accept the licence |
| `No profiles for 'com.distillative.ralphvc' were found` | Bundle id collides with another developer's | Edit `ios-app/project.yml` → change `PRODUCT_BUNDLE_IDENTIFIER` |
| `App installation failed: Could not write to the device` | iPhone locked or pending trust prompt | Unlock the phone; *Settings → General → VPN & Device Management* → trust the developer |
| `Ralph couldn't reach the orchestrator` | iPhone can't reach your Mac | Make sure both are on the same Wi-Fi; firewall isn't blocking 7878 |
| TTS isn't using the Ralph voice | Voice not installed | iPhone *Settings → Accessibility → Spoken Content → Voices → English → Ralph* (download) |
| `device install hangs at "preparing debugger support"` | First-time pairing for that Xcode version | `xcrun devicectl manage pair`, then re-run `./setup.sh` |

## Reading the logs

The server logs go to `/tmp/ralphvc-server.log`:

```bash
tail -f /tmp/ralphvc-server.log
```

The iOS app logs go to the simulator/device console — `Console.app` on the
Mac, filtered by process *RalphVC*.

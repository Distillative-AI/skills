---
name: ralph-vc-ios
description: The iPhone/iPad-side companion to the `ios-development` skill. Ships a SwiftUI app called Ralph VC (Vibe Coder) that lets a user dictate iOS feature requests on the go, forwards them to a locally-running Sonnet orchestrator, and reads the answer back through native iOS TTS using the Ralph voice when installed. Pair this skill with `ios-development` so the iPhone app, the macOS-side build tools, and the BDD/Virtual-User test loop all live under one workflow.
license: Apache-2.0
---

<!--
  Authored by Chase Eddies <source@distillative.ai>.
  Coding assistant: Claude Code Cloud.
-->

# Ralph VC — iOS-side vibe coder

`ralph-vc-ios` is the **iOS app you carry in your pocket** that turns
Claude Code Cloud into a hands-free vibe-coding surface. It pairs with
the macOS-side `ios-development` skill: Ralph VC handles voice in,
voice out, and the chat UI on the phone; the macOS workspace handles
build, deploy, BDD, code review, and deep research.

```
[ iPhone — Ralph VC ]   STT → prompt → HTTPS POST →   [ macOS — orchestrator ]
                                                       │
                                                       ├─► run_deploy
                                                       ├─► run_bdd
                                                       ├─► virtual_user_action
                                                       ├─► research_arxiv
                                                       ├─► research_ios_feature
                                                       └─► adversarial / constructive review
[ iPhone ]   ← speak via Ralph TTS ← reply ← HTTPS ←
```

## When to use

Trigger this skill when the user wants to:

- Ship the iPhone app that drives Claude Code Cloud over voice.
- Wire the iOS Speech framework + AVSpeechSynthesizer into a chat shell
  with Ralph's persona.
- Stand up the small local HTTP server (`server/server.py`) that the
  iOS app POSTs to, which delegates to the `ios-development`
  orchestrator.
- Add or change a Ralph behaviour (system prompt, voice resolver,
  accessibility wiring).

## Goal

**Maximal UI/UX performance on iOS** — the same north star as the
`ios-development` skill. Ralph VC must launch fast, scroll at 120 fps,
never block the main thread, and remain fully usable under VoiceOver,
Dynamic Type, and Reduced Motion.

## Run it on your iPhone — one command

> **See `RUNNING_ON_IPHONE.md` for the full walkthrough.**

On your Mac (Xcode 15+ installed, iPhone tethered):

```bash
export ANTHROPIC_API_KEY=sk-ant-...
./setup.sh --device --team-id ABCDE12345
```

`setup.sh` checks prerequisites, runs `xcodegen generate` against
`ios-app/project.yml` to materialise `RalphVC.xcodeproj`, starts the
local server in the background, and shells out to the sibling
`ios-development` skill's `app/deploy.py` to build + sign + install +
launch the app on your phone. To iterate without a cable:
`./setup.sh --simulator`. To open the in-app gear icon → paste the
endpoint + bearer token printed by `setup.sh`, save to Keychain, and
tap the mic.

## Repo layout

```
ralph-vc-ios/
├── SKILL.md
├── ios-app/RalphVC/
│   ├── RalphVCApp.swift         # @main + AppSession
│   ├── ChatView.swift           # SwiftUI chat surface
│   ├── ChatViewModel.swift      # @MainActor view model
│   ├── RalphAgent.swift         # POSTs prompts to the macOS orchestrator
│   ├── RalphVoice.swift         # TTS + STT + Ralph voice resolver
│   ├── Settings.swift           # endpoint URL, voice prefs
│   └── Info.plist
├── server/
│   ├── server.py                # tiny HTTP shim around the orchestrator
│   └── ralphvc.toml             # default endpoint + auth config
├── iosdeploy.toml               # defaults for `python ../ios-development/app/deploy.py`
├── requirements.txt
└── tests/                       # functional tests for the server shim
```

## The on-device experience

1. User taps the mic button (or says "hey Ralph" if Listen-Always is on).
2. STT converts speech → text using `SFSpeechRecognizer`, on-device when
   the device supports it.
3. The text is rendered in the chat as the user message.
4. `RalphAgent` POSTs `{ "prompt": "..." }` to
   `http://<workspace-host>:7878/v1/orchestrate`.
5. The server delegates to the `ios-development` orchestrator
   (`run_orchestrator(...)`), which talks to Claude Sonnet 4.6 via the
   Anthropic SDK with prompt caching enabled.
6. The reply is rendered in the chat AND announced via TTS using the
   Ralph voice (resolver: any `AVSpeechSynthesisVoice` whose
   `identifier` contains `"Ralph"`; falls back to the highest-quality
   system voice).

## Server shim

`server/server.py` is a ~80-line `http.server`-based shim — no Flask,
no FastAPI dependency. It exposes:

- `POST /v1/orchestrate` — body `{ "prompt": "...", "max_turns": 6 }`,
  returns `{ "final_text": "...", "cache_read_input_tokens": ..., "turns": ... }`.
- `GET /healthz` — for the iOS app to probe reachability before
  popping the keyboard.

The shim is **localhost-only by default** and gated behind a bearer
token loaded from `RALPHVC_BEARER` (or from `server/ralphvc.toml`). The
iOS app puts the token in the `Authorization: Bearer <token>` header.

## Pairing with `ios-development`

`server/server.py` imports `app.orchestrator.run_orchestrator` from the
sibling `ios-development` skill. Both skills are intended to be
installed together via the `anthropic-agent-skills` marketplace; the
server fails fast with a friendly message if the import path can't be
resolved, telling the user to install `ios-development` alongside this
skill.

## Spec-driven development

Ralph VC follows the same SDD/BDD loop the `ios-development` skill
teaches:

1. Add a Gherkin scenario in `ios-development/bdd/features/` that
   exercises the new behaviour through the Virtual User Agent.
2. Run `python ios-development/bdd/runner.py` — must fail (red).
3. Add the SwiftUI/Swift change in `ios-app/RalphVC/`.
4. Re-deploy with `python ios-development/app/deploy.py` from this
   directory (defaults pulled from `iosdeploy.toml`).
5. Re-run BDD until green.
6. Run `adversarial_review` + `constructive_review` plugins on the
   diff.

## Guidelines

- **Voice first, text second.** Every flow must be reachable without
  tapping. Mic button + voice activity detection are the primary input.
- **Never block the main thread.** STT, TTS, and HTTPS calls go through
  Swift Concurrency (`async`/`await`, `@MainActor` for UI updates).
- **VoiceOver-clean by construction.** Every interactive element ships
  with `accessibilityLabel` + `accessibilityIdentifier`.
- **Localhost by default.** The server shim refuses non-loopback
  connections unless explicitly enabled in `ralphvc.toml`.
- **Bearer-token only.** No anonymous endpoints. The iOS app stores the
  token in the keychain, not in `UserDefaults`.

## Common pitfalls

| Symptom | Cause | Fix |
| --- | --- | --- |
| `Ralph couldn't reach the orchestrator` | Server not running | `python server/server.py` from the workspace host |
| 401 from `/v1/orchestrate` | Missing bearer token | Set `RALPHVC_BEARER` and matching token in iOS keychain |
| TTS voice is not Ralph | Voice not installed | iOS Settings → Accessibility → Spoken Content → Voices → English → Ralph |
| STT returns empty strings | Microphone permission denied | Re-prompt via Settings → Privacy → Microphone |
| `ImportError: app.orchestrator` from server | `ios-development` not installed | Install both skills from the marketplace |

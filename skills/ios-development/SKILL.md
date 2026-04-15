---
name: ios-development
description: End-to-end iOS development toolkit for vibe-coding native iOS apps via Claude Code Cloud and deploying them locally to a simulator or a tethered device — entirely from an iOS phone. Includes a Sonnet-powered orchestrator (Claude Code API + prompt caching), a black-box Virtual User Agent that drives the UI, a spec-driven BDD methodology with passing tests, a 24h-cached SDK index, and AgentSkills-format WASM plugins for deep-research over arXiv + iOS feature feeds and for adversarial / constructive code review.
license: Apache-2.0
---

<!--
  Authored by Chase Eddies <source@distillative.ai>.
  Coding assistant: Claude Code Cloud (the web/cloud edition of Claude Code,
  used here from an iOS mobile device through claude.ai/code).
-->

# iOS Development

This skill turns Claude Code Cloud into a full iOS dev studio that the user can drive **from an iPhone**. It bundles four things:

1. **A Sonnet-powered orchestrator app** (`app/orchestrator.py`) that takes natural-language instructions, talks to Claude Sonnet 4.6 via the **Claude Code API** (Anthropic SDK), and dispatches three local tools: `run_deploy`, `run_bdd`, `virtual_user_action`. Prompt caching is on by default and the system prompt is byte-stable across requests so subsequent turns hit the cache.
2. **A local-deploy CLI** (`app/deploy.py`) that builds, installs, and launches the project on the iOS Simulator or a tethered device using only `xcodebuild` + `xcrun`. No need to open Xcode.app.
3. **A Virtual User Agent** (`agent/`) — a black-box driver that taps, types, screenshots, and asserts on labelled UI elements. Pluggable backends: `SimctlBackend` for real simulators, `MockBackend` for deterministic CI / spec-driven design.
4. **WASM/AgentSkills-format plugins** (`plugins/`) for deep research over arXiv + iOS feature feeds with 24h TTL caching + offline RAG, and for adversarial + constructive code review aligned to the **maximal UI/UX performance** north star.

> **The vibe-coding loop**: user speaks on iPhone → Ralph (in-app agent) transcribes via iOS STT → forwards prompt to the macOS-side orchestrator → orchestrator calls Sonnet via the Claude Code API → Sonnet decides what to deploy/test → tools run locally → Ralph speaks the answer back through iOS TTS using the **Ralph voice** when installed.

## When to use

Trigger this skill when the user wants to:

- Vibe-code an iOS app from their phone via Claude Code Cloud.
- Scaffold, build, install, or launch a SwiftUI / UIKit project from the CLI.
- Write spec-driven BDD scenarios that drive the app via the Virtual User Agent.
- Run code review focused on UI/UX performance (adversarial + constructive).
- Pull in recent literature (arXiv) or iOS feature/community updates while coding.
- Diagnose `xcodebuild` / signing errors without booting Xcode.

## Spec-driven BDD development workflow

This is the **primary development loop** the skill teaches Claude:

```
1. SPEC      Write a Gherkin .feature describing the user-visible behaviour.
2. STEPS     Add or extend step definitions in bdd/steps/ that drive the app
             through the Virtual User Agent (tap, type, assert_visible, ...).
3. RED       Run `python bdd/runner.py` — the suite must fail because the
             implementation does not exist yet.
4. IMPL      Write the smallest SwiftUI/UIKit change that makes the failing
             scenario pass. Deploy with `python app/deploy.py`.
5. GREEN     Re-run the BDD suite. If green, commit. If not, iterate.
6. CRIT      Invoke the `adversarial_review` and `constructive_review`
             plugins on the diff. Address critical findings before moving on.
7. RESEARCH  When stuck on an algorithmic or platform-API question, invoke
             the `research_arxiv` or `research_ios_feature` plugin. Both
             cache results for 24h and support offline RAG so the iOS host
             can answer follow-ups without network.
```

The "iOS_SDK_SNAPSHOT" surfaced to the orchestrator on every turn comes from `app/sdk_cache.py` — a 24h-cached view of `xcrun`/`xcodebuild` versions, recommended SwiftPM packages, and which companion CLIs (`devicectl`, `ios-deploy`, `idb`, `xcodegen`, `xcbeautify`) are installed. The Xcode install itself is **out of scope** — the cache only tracks what changes more often than Xcode.

## Decision tree

```
User request
├── "Make / scaffold a new iOS app"      → scripts/new_project.py
├── "Build / test"                        → scripts/build.sh (xcodebuild wrapper)
├── "Deploy to simulator"                 → app/deploy.py --target simulator
├── "Deploy to device"                    → app/deploy.py --target device --team-id ...
├── "Drive the UI / write a scenario"     → bdd/features/*.feature + agent/
├── "Critique my code"                    → plugins/code-review (both reviewers)
├── "What does the literature say?"       → plugins/arxiv-research
├── "What's new in iOS / Swift?"          → plugins/ios-feature-index
└── "Just do it for me, here's a prompt"  → app/orchestrator.py "<prompt>"
```

## Layout

```
ios-development/
├── SKILL.md                       # this file
├── requirements.txt
├── app/
│   ├── deploy.py                  # local deploy CLI (xcodebuild + simctl/devicectl)
│   ├── orchestrator.py            # Sonnet-powered NL driver, Claude Code API + caching
│   └── sdk_cache.py               # 24h TTL iOS SDK / toolchain cache
├── agent/
│   ├── virtual_user.py            # high-level black-box UI agent
│   └── backends.py                # SimctlBackend + MockBackend
├── bdd/
│   ├── features/vibe_code.feature # Gherkin spec
│   ├── steps/vibe_steps.py
│   ├── environment.py
│   └── runner.py
├── plugins/                       # AgentSkills-format WASM plugins
│   ├── README.md
│   ├── _loader/                   # dev (Python) loader; WASM stub via wasmtime
│   ├── arxiv-research/            # 24h-cached arXiv index + offline RAG
│   ├── ios-feature-index/         # Apple/Swift-evolution/community feeds, 24h, RAG
│   └── code-review/               # adversarial + constructive sub-agents (Sonnet)
├── example/HelloIPhone/           # SwiftUI demo with TTS/STT + Ralph voice
├── tests/                         # pytest suite (24 tests, all passing)
├── references/                    # SwiftUI patterns, codesigning, xcodebuild
└── scripts/                       # build.sh, new_project.py
```

## The local deployer app

`app/deploy.py` is the bedrock — every other piece eventually shells out to it.

```bash
# Use the orchestrator from the example dir (defaults from iosdeploy.toml).
python app/deploy.py

# Or be explicit:
python app/deploy.py --project HelloIPhone.xcodeproj \
                     --scheme HelloIPhone \
                     --target simulator
```

It picks a destination (`xcrun simctl` for simulators, `xcrun devicectl` then `ios-deploy` for devices), runs `xcodebuild build`, locates the produced `.app` via `-showBuildSettings`, installs and launches, then streams the device/simulator log filtered to the launched bundle id.

## The orchestrator app (Sonnet + Claude Code API)

`app/orchestrator.py` is the natural-language entry point — the user-facing "vibe" surface.

```bash
python app/orchestrator.py "deploy MyApp to my iPhone and verify the title shows"
```

Defaults: `claude-sonnet-4-6` with `thinking={"type":"adaptive"}`, prompt caching on (the system prompt + tool list is the cacheable prefix; the volatile user message goes after). Tool execution stays local, so signing keys and project files never leave the workspace. Ralph (the in-app iOS agent in `example/HelloIPhone/RalphAgent.swift`) is the iOS-side counterpart that POSTs prompts here.

## The Virtual User Agent

`agent/virtual_user.py` is the high-level driver. It is intentionally tiny:

```python
from agent import VirtualUser

vu = VirtualUser.for_simulator(bundle_id="com.example.MyApp")
vu.boot(device="iPhone 15")
vu.install_and_launch(Path("/path/to/MyApp.app"))
vu.wait_for("Login")
vu.fill_field("Email", "ada@example.com")
vu.tap("Continue")
vu.assert_visible("Welcome")
```

Backends:

- `SimctlBackend` — drives a real iOS Simulator via `xcrun simctl`, falls back to `idb` for taps/gestures when needed.
- `MockBackend` — deterministic, in-memory; lets BDD scenarios run on CI without a Mac, and lets Claude iterate on Gherkin specs without a simulator.

## Plugins (AgentSkills format, runs as WASM)

Plugins live in `plugins/`. Each plugin is an AgentSkills-format folder (`SKILL.md` + `plugin.toml` + handler). Today they run via a pure-Python loader in `plugins/_loader` so contributors can iterate without a WASM toolchain; switching to a WASI host (`wasmtime`) is a single environment-variable flag and is documented in the loader.

| Plugin              | Tool(s)                                           | What it does                                                                                  |
| ------------------- | ------------------------------------------------- | --------------------------------------------------------------------------------------------- |
| `arxiv-research`    | `research_arxiv`                                  | Search arXiv, cache 24h, offline RAG over the cached corpus.                                  |
| `ios-feature-index` | `research_ios_feature`                            | Aggregate Apple Developer + Swift Evolution + community feeds; 24h cache; offline RAG.        |
| `code-review`       | `adversarial_review`, `constructive_review`       | Two Sonnet sub-agents reviewing for **maximal UI/UX performance on iOS**.                     |

Both research plugins implement the **24h refresh contract**: if any source is older than 24h we hit its API and rebuild the embedding index; if not, we return the cached snapshot. The embedding scheme is a deterministic hashing-vectorizer with no external deps so the cache can be shipped to an iOS host for fully-offline RAG.

## The example app — Ralph + TTS + STT

`example/HelloIPhone/` is a SwiftUI app that exercises the full loop. It uses:

- `AVSpeechSynthesizer` for TTS, with a `preferredVoice(for:)` resolver that picks **Ralph** when installed (any voice identifier containing "Ralph") and falls back to the highest-quality system voice.
- `SFSpeechRecognizer` for STT, with `requiresOnDeviceRecognition = true` when the device supports it.
- `UIAccessibility.post(notification: .announcement, ...)` so VoiceOver users get the same audio.
- `RalphAgent.swift` as the chat broker between the iPhone and the local orchestrator (`POST /v1/orchestrate`).

## Reference material

- `references/swiftui_patterns.md` — opinionated SwiftUI / MVVM patterns.
- `references/codesigning.md` — how to diagnose signing errors.
- `references/xcodebuild_cheatsheet.md` — every `xcodebuild` flag worth memorising.
- `plugins/README.md` — plugin authoring guide.

## Testing this skill

```bash
pip install -r requirements.txt
pytest tests/                                  # 24 tests, all passing
PYTHONPATH=. IOS_LOCALDEPLOY_BDD=mock python -m behave bdd/features/
```

Both suites are runnable on Linux CI without a Mac thanks to `MockBackend` and the fixture mode of the code-review plugin (`IOS_LOCALDEPLOY_REVIEW_FIXTURE=1`).

## Guidelines

- **Goal: maximal UI/UX performance on iOS.** Every code-review pass and every spec must judge the change against this north star.
- **Never hand-edit `project.pbxproj`** unless absolutely necessary.
- **Always `--help` the bundled scripts first.** They are designed as black boxes.
- **Surface signing errors verbatim.** They are precise.
- **Keep simulator builds the default** when iterating.
- **Confirm before installing on a device.**
- **Cache aggressively, invalidate honestly.** Both the SDK cache and the plugin caches use a 24h TTL. Do not bypass it casually — that defeats the offline-RAG story for the iOS host.

## Common pitfalls

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| `No such module 'SwiftUI'` from `xcodebuild` | Wrong `-destination` (macOS by default) | Pass `-destination 'platform=iOS Simulator,...'` |
| `Code Signing Error: No profiles for 'com.example.app'` | Bundle id not in any provisioning profile | Use `--team-id` + automatic signing, or change the bundle id |
| Device install hangs at "preparing debugger support" | First-time pairing for that Xcode version | Run `xcrun devicectl manage pair` once, then retry |
| Orchestrator says cache reads = 0 across turns | Silent invalidator in the prefix | The prompt is byte-stable in this skill — check for any custom system text you injected |
| Ralph voice not used | Voice not installed | Settings → Accessibility → Spoken Content → Voices → English → Ralph |

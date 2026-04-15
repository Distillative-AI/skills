---
name: code-review
description: Pair of code-review sub-agents for the ios-development orchestrator. The "adversarial" agent role-plays a hostile reviewer hunting for security holes, race conditions, force-unwraps, and signing footguns. The "constructive" agent acts as a supportive senior engineer focused on clarity, naming, testability, and what to keep doing well. Both spawn as short-lived Sonnet sub-agents.
license: Apache-2.0
---

<!--
  Authored by Chase Eddies <source@distillative.ai>.
  Coding assistant: Claude Code Cloud.
-->

# Code-review plugin

Exposes two tools to the orchestrator:

- `adversarial_review(code)` — red-team mindset. Returns a JSON list of
  numbered findings, each tagged `severity: low|med|high|critical` and
  ideally with a concrete reproduction step. The reviewer is instructed
  to assume any input is adversarial and any user is malicious.
- `constructive_review(code)` — supportive senior engineer mindset.
  Returns the same JSON shape but each finding is paired with a
  `keep_doing` field that surfaces what the author got right.

Both run as one-shot Sonnet calls with adaptive thinking and prompt
caching of the static system prompt. Both have a deterministic fixture
mode (toggled via `IOS_LOCALDEPLOY_REVIEW_FIXTURE=1`) so the test
suite can verify the orchestrator wiring without burning API quota.

## Use them together

The orchestrator will normally invoke **both** in parallel after a code
change so the user sees the harshest critique and the most generous
critique side-by-side. The Gherkin BDD scenarios use this pattern.

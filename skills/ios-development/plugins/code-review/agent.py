"""code-review plugin: adversarial + constructive sub-agents.

Both agents are aligned on a single shared goal — **maximal UI and UX
performance on iOS** — and judge the code accordingly. Reviews are
returned as JSON so the orchestrator can render them side-by-side.

Authored by Chase Eddies <source@distillative.ai>.
"""

from __future__ import annotations

import json
import os
import re
import textwrap
from typing import Any


# ---------------------------------------------------------------------------
# Shared system prompts
# ---------------------------------------------------------------------------


_SHARED_GOAL = textwrap.dedent("""
    THE NORTH-STAR GOAL is **maximal UI and UX performance on iOS**:
    - 60–120 fps scrolling and animations, no dropped frames
    - sub-100 ms perceived latency for every user-initiated action
    - small launch / cold-start time
    - low memory pressure (no leaks, no retain cycles, no large unbounded caches)
    - accessibility compliance (Dynamic Type, VoiceOver, reduced motion)

    Judge the code primarily against this goal. Other concerns (style, naming)
    matter only insofar as they protect or undermine it.
""").strip()


_ADVERSARIAL_PROMPT = f"""You are an extremely hostile senior iOS performance
reviewer. Your job is to find every way the supplied code is going to ship
slow, janky, leaky, or insecure. Be specific. Do not soften your tone. Cite
the exact line / construct that is wrong and the exact mechanism by which it
hurts the user. Assume the worst about input data, network conditions, and
device thermals.

{_SHARED_GOAL}

Return JSON of shape:
{{
  "findings": [
    {{"id": 1, "severity": "critical|high|med|low",
      "category": "perf|memory|layout|main_thread|security|accessibility",
      "where": "<construct or symbol>",
      "problem": "<one-sentence problem>",
      "repro": "<how to observe it on a real device>",
      "fix": "<concrete fix>"}}
  ]
}}
Output ONLY that JSON, nothing else.
"""


_CONSTRUCTIVE_PROMPT = f"""You are a supportive but rigorous senior iOS
engineer doing a friendly review aimed at shipping the best possible UX.
For each issue, also call out the matching thing the author is doing well,
so the conversation feels collaborative rather than punitive.

{_SHARED_GOAL}

Return JSON of shape:
{{
  "findings": [
    {{"id": 1, "severity": "critical|high|med|low",
      "category": "perf|memory|layout|main_thread|security|accessibility",
      "where": "<construct or symbol>",
      "problem": "<one-sentence problem>",
      "fix": "<concrete fix>",
      "keep_doing": "<the related thing the author already got right>"}}
  ]
}}
Output ONLY that JSON, nothing else.
"""


# ---------------------------------------------------------------------------
# Sonnet driver
# ---------------------------------------------------------------------------


def _call_sonnet(system_prompt: str, code: str, context: str, max_findings: int) -> str:
    if os.environ.get("IOS_LOCALDEPLOY_REVIEW_FIXTURE"):
        return _fixture_response(code, max_findings)

    try:
        import anthropic  # type: ignore[import-not-found]
    except ModuleNotFoundError:
        return _fixture_response(code, max_findings, note="anthropic SDK missing")

    if not os.environ.get("ANTHROPIC_API_KEY"):
        return _fixture_response(code, max_findings, note="ANTHROPIC_API_KEY unset")

    client = anthropic.Anthropic()
    user_message = textwrap.dedent(f"""
        Maximum findings: {max_findings}.
        Context: {context or "(none provided)"}

        --- BEGIN CODE ---
        {code}
        --- END CODE ---
    """).strip()

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4000,
        thinking={"type": "adaptive"},
        system=[{
            "type": "text",
            "text": system_prompt,
            "cache_control": {"type": "ephemeral"},  # cacheable across reviews
        }],
        messages=[{"role": "user", "content": user_message}],
    )
    return "\n".join(
        b.text for b in response.content if getattr(b, "type", None) == "text"
    )


def _fixture_response(code: str, max_findings: int, *, note: str = "fixture mode") -> str:
    """Deterministic fixture used by tests and offline runs.

    The "review" surfaces a couple of well-known iOS perf footguns that are
    almost certainly present in any non-trivial Swift snippet, so the
    pipeline can be exercised end-to-end without an API key.
    """
    findings: list[dict[str, Any]] = []
    if "Date()" in code or "Date.now" in code:
        findings.append({
            "id": len(findings) + 1,
            "severity": "med",
            "category": "perf",
            "where": "Date() / Date.now in render path",
            "problem": "Allocating Date in body recomputes per layout pass.",
            "fix": "Hoist the timestamp out of body or @State it.",
            "keep_doing": "you are at least using Foundation's Date, not a string clock",
        })
    if re.search(r"\bForEach\b.*\b\\\.self\b", code) or "id: \\.self" in code:
        findings.append({
            "id": len(findings) + 1,
            "severity": "high",
            "category": "layout",
            "where": "ForEach using \\.self",
            "problem": "Triggers full diff on every state change; jank on long lists.",
            "fix": "Conform the model to Identifiable with a stable id.",
            "keep_doing": "the list is at least laid out with ForEach rather than VStack",
        })
    if "DispatchQueue.main.sync" in code:
        findings.append({
            "id": len(findings) + 1,
            "severity": "critical",
            "category": "main_thread",
            "where": "DispatchQueue.main.sync",
            "problem": "Will deadlock if invoked from the main thread.",
            "fix": "Use DispatchQueue.main.async or @MainActor isolation.",
            "keep_doing": "you correctly identified that this work belongs on the main queue",
        })
    if not findings:
        findings.append({
            "id": 1,
            "severity": "low",
            "category": "perf",
            "where": "<entire snippet>",
            "problem": "Fixture review found no obvious red flags.",
            "fix": "Run on a real device with Instruments → Animation Hitches.",
            "keep_doing": "snippet is small, focused, and easy to reason about",
        })
    return json.dumps(
        {"findings": findings[:max_findings], "_note": note},
        indent=2,
    )


# ---------------------------------------------------------------------------
# Tool entrypoints (referenced from plugin.toml).
# ---------------------------------------------------------------------------


def adversarial_review(payload: dict[str, Any]) -> str:
    return _call_sonnet(
        _ADVERSARIAL_PROMPT,
        payload["code"],
        payload.get("context", ""),
        int(payload.get("max_findings", 10)),
    )


def constructive_review(payload: dict[str, Any]) -> str:
    return _call_sonnet(
        _CONSTRUCTIVE_PROMPT,
        payload["code"],
        payload.get("context", ""),
        int(payload.get("max_findings", 10)),
    )

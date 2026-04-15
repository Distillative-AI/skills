"""ios-localdeploy orchestrator — natural-language deploy + UI driver.

This is the user-facing "app that lets you deploy locally to iOS". It is a
small CLI that takes natural-language instructions ("deploy MyApp to my
iPhone and verify the login screen appears") and dispatches them to the
right tools by talking to **Claude Sonnet 4.6** via the Anthropic SDK
(a.k.a. the Claude Code API). Sessions are routed against Claude Code
Cloud so the user can drive everything from an iOS mobile device through
claude.ai/code.

Authored by Chase Eddies <source@distillative.ai>.
Coding assistant: Claude Code Cloud.

Design notes
------------
- Default model: ``claude-sonnet-4-6`` (overridable via ``--model``).
- Adaptive thinking is on by default so Sonnet can reason about
  multi-step iOS deploy + test sequences.
- Prompt caching is on by default. The system prompt + the JSON tool list
  + the static skill snippet are stable across requests and are placed
  before the volatile user message, so the second turn of any session
  hits the cache. We verify by reading
  ``response.usage.cache_read_input_tokens``.
- The orchestrator exposes three local tools to the model:
  ``run_deploy``, ``run_bdd``, and ``virtual_user_action``. Tool execution
  happens locally (the CLI is the harness), so secrets stay on the user's
  workspace.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Static system prompt (stable → cacheable).
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are the iOS deployment orchestrator that ships with the
`ios-development` Claude Code skill. You are running locally on the user's
macOS workspace and you are talking to the user (who is on an iOS device,
through Claude Code Cloud).

The product you live inside lets the user **vibe-code iOS apps via the
Claude Code API and deploy locally to iOS — from iOS**. Your job is to
make that workflow feel weightless: small natural-language requests in,
working builds on the user's phone out, with a passing spec-driven BDD
suite to prove it.

You will receive an iOS_SDK_SNAPSHOT block in each user turn carrying a
24-hour-cached view of the local toolchain (Xcode/SDK versions, Swift
version, recommended SwiftPM packages, available companion CLIs). Use it
to pick correct API surfaces and to decide which deploy fallback path
(`devicectl` vs `ios-deploy`) is even available. Xcode itself is out of
scope — assume it is installed.

Translate natural-language requests like:

- "deploy MyApp to my iPhone"
- "build for the simulator and tap Login"
- "run the BDD suite, then redeploy"

…into one or more calls to the locally-available tools below. Always:

1. Use the cheapest/fastest path that satisfies the request. Prefer the
   simulator when the user does not explicitly ask for a device.
2. Confirm before doing anything irreversible (replacing a device install,
   reinstalling over an App Store build, deleting derived data).
3. Stream progress to the user — call one tool, observe the output, and
   only then plan the next step.

Available tools:

- `run_deploy(target, scheme=None, project=None, ...)` — invokes
  `app/deploy.py`, the bundled local-deploy CLI.
- `run_bdd(feature=None)` — invokes the spec-driven BDD runner that
  exercises the app via the Virtual User Agent.
- `virtual_user_action(action, label=None, x=None, y=None, text=None)`
  — drives a single UI interaction (tap, type, screenshot, assert).

Refuse requests that try to install on a device the user has not
authorized, or that disable code signing for a device build.
"""


# ---------------------------------------------------------------------------
# Tool definitions for the Anthropic SDK tool runner.
# ---------------------------------------------------------------------------


def tool_definitions() -> list[dict[str, Any]]:
    """The static tool list. Stable across requests → cacheable."""
    return [
        {
            "name": "run_deploy",
            "description": "Build, install, and launch the iOS app locally via app/deploy.py.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "target": {"type": "string", "enum": ["simulator", "device"]},
                    "project": {"type": "string"},
                    "workspace": {"type": "string"},
                    "scheme": {"type": "string"},
                    "device": {"type": "string"},
                    "team_id": {"type": "string"},
                    "configuration": {"type": "string"},
                },
                "required": ["target"],
            },
        },
        {
            "name": "run_bdd",
            "description": "Run the spec-driven BDD suite (Gherkin features in bdd/features/).",
            "input_schema": {
                "type": "object",
                "properties": {
                    "feature": {"type": "string", "description": "Optional feature file to run alone."},
                    "tags": {"type": "string", "description": "behave --tags expression"},
                },
            },
        },
        {
            "name": "virtual_user_action",
            "description": "Drive one Virtual User UI action against the running app.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["tap", "tap_at", "type_text", "screenshot", "assert_visible", "wait_for"],
                    },
                    "label": {"type": "string"},
                    "x": {"type": "integer"},
                    "y": {"type": "integer"},
                    "text": {"type": "string"},
                    "path": {"type": "string"},
                    "timeout": {"type": "number"},
                },
                "required": ["action"],
            },
        },
    ]


# ---------------------------------------------------------------------------
# Local tool dispatch.
# ---------------------------------------------------------------------------


SKILL_ROOT = Path(__file__).resolve().parent.parent


@dataclass
class ToolDispatch:
    """Routes tool_use blocks to local executables. Used by the agent loop."""

    workdir: Path = field(default_factory=Path.cwd)
    dry_run: bool = False

    def run(self, name: str, payload: dict[str, Any]) -> str:
        if name == "run_deploy":
            return self._run_deploy(payload)
        if name == "run_bdd":
            return self._run_bdd(payload)
        if name == "virtual_user_action":
            return self._virtual_user(payload)
        return f"unknown tool {name!r}"

    # ---- per-tool --------------------------------------------------------

    def _run_deploy(self, p: dict[str, Any]) -> str:
        argv: list[str] = [sys.executable, str(SKILL_ROOT / "app" / "deploy.py")]
        for k in ("project", "workspace", "scheme", "configuration", "device", "team_id"):
            v = p.get(k)
            if v:
                argv += [f"--{k.replace('_', '-')}", str(v)]
        argv += ["--target", str(p["target"])]
        return self._exec(argv)

    def _run_bdd(self, p: dict[str, Any]) -> str:
        argv = [sys.executable, str(SKILL_ROOT / "bdd" / "runner.py")]
        if p.get("feature"):
            argv += ["--feature", p["feature"]]
        if p.get("tags"):
            argv += ["--tags", p["tags"]]
        return self._exec(argv)

    def _virtual_user(self, p: dict[str, Any]) -> str:
        # We import lazily so the orchestrator can be used in environments
        # without the simctl backend dependencies installed.
        from ..agent import VirtualUser

        vu = VirtualUser.for_simulator()
        action = p["action"]
        if action == "tap":
            vu.tap(p["label"]); return f"tapped {p['label']!r}"
        if action == "tap_at":
            vu.tap_at(p["x"], p["y"]); return f"tapped at ({p['x']},{p['y']})"
        if action == "type_text":
            vu.type_text(p["text"]); return f"typed {len(p['text'])} chars"
        if action == "screenshot":
            out = vu.screenshot(Path(p.get("path", "/tmp/ios-screenshot.png")))
            return f"screenshot saved to {out}"
        if action == "assert_visible":
            vu.assert_visible(p["label"]); return f"{p['label']!r} is visible"
        if action == "wait_for":
            vu.wait_for(p["label"], timeout=p.get("timeout"))
            return f"{p['label']!r} appeared"
        return f"unknown action {action!r}"

    # ---- helper ----------------------------------------------------------

    def _exec(self, argv: list[str]) -> str:
        if self.dry_run:
            return "(dry-run) " + " ".join(shlex.quote(a) for a in argv)
        proc = subprocess.run(argv, cwd=self.workdir, text=True, capture_output=True)
        return (
            f"$ {' '.join(shlex.quote(a) for a in argv)}\n"
            f"exit={proc.returncode}\n"
            f"--- stdout ---\n{proc.stdout}\n"
            f"--- stderr ---\n{proc.stderr}"
        )


# ---------------------------------------------------------------------------
# Anthropic SDK driver.
# ---------------------------------------------------------------------------


def run_orchestrator(
    user_prompt: str,
    *,
    model: str = "claude-sonnet-4-6",
    max_turns: int = 6,
    dry_run: bool = False,
    workdir: Optional[Path] = None,
) -> dict[str, Any]:
    """Drive Claude Sonnet via the Anthropic SDK with prompt caching enabled.

    Returns a small structured summary (final text + cache statistics) so
    the CLI and tests can both make assertions about the run.
    """

    try:
        import anthropic  # type: ignore[import-not-found]
    except ModuleNotFoundError as e:
        raise SystemExit(
            "the anthropic SDK is not installed. `pip install anthropic` (>=0.40)."
        ) from e

    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit("ANTHROPIC_API_KEY is not set in the environment.")

    client = anthropic.Anthropic()
    dispatch = ToolDispatch(workdir=workdir or Path.cwd(), dry_run=dry_run)

    # Stable prefix → cache it. Render order is tools → system → messages,
    # so a cache_control marker on the last system block caches both.
    system_blocks = [{
        "type": "text",
        "text": SYSTEM_PROMPT,
        "cache_control": {"type": "ephemeral"},
    }]

    messages: list[dict[str, Any]] = [
        {"role": "user", "content": user_prompt}
    ]

    final_text = ""
    cache_reads = 0
    cache_writes = 0

    for _ in range(max_turns):
        response = client.messages.create(
            model=model,
            max_tokens=16000,
            thinking={"type": "adaptive"},
            system=system_blocks,
            tools=tool_definitions(),
            messages=messages,
        )
        cache_reads += getattr(response.usage, "cache_read_input_tokens", 0) or 0
        cache_writes += getattr(response.usage, "cache_creation_input_tokens", 0) or 0

        # Echo full content back into history, including thinking + tool_use.
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn":
            final_text = "\n".join(
                b.text for b in response.content if getattr(b, "type", None) == "text"
            )
            break

        if response.stop_reason != "tool_use":
            # pause_turn or refusal — surface verbatim.
            final_text = f"[stop_reason={response.stop_reason}]"
            break

        tool_results: list[dict[str, Any]] = []
        for block in response.content:
            if getattr(block, "type", None) != "tool_use":
                continue
            try:
                result = dispatch.run(block.name, dict(block.input))
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result,
                })
            except Exception as exc:  # surface to the model
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": f"tool error: {exc}",
                    "is_error": True,
                })
        messages.append({"role": "user", "content": tool_results})

    return {
        "final_text": final_text,
        "cache_read_input_tokens": cache_reads,
        "cache_creation_input_tokens": cache_writes,
        "turns": len(messages),
        "model": model,
    }


# ---------------------------------------------------------------------------
# CLI entry point.
# ---------------------------------------------------------------------------


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(
        prog="ios-localdeploy-orchestrator",
        description="Natural-language iOS deployment driver, powered by Claude Sonnet via Claude Code Cloud.",
    )
    p.add_argument("prompt", nargs="+", help="natural-language instruction")
    p.add_argument("--model", default="claude-sonnet-4-6")
    p.add_argument("--max-turns", type=int, default=6)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--json", dest="emit_json", action="store_true")
    args = p.parse_args(argv)

    summary = run_orchestrator(
        " ".join(args.prompt),
        model=args.model,
        max_turns=args.max_turns,
        dry_run=args.dry_run,
    )
    if args.emit_json:
        print(json.dumps(summary, indent=2))
    else:
        print(summary["final_text"])
        print()
        print(
            f"[cache reads: {summary['cache_read_input_tokens']}  "
            f"writes: {summary['cache_creation_input_tokens']}  "
            f"turns: {summary['turns']}  model: {summary['model']}]"
        )
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))

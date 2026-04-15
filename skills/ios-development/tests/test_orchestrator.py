"""Functional tests for the Sonnet-powered orchestrator's local pieces.

We do NOT call the real Anthropic API here. Instead we exercise the
ToolDispatch wiring (so we know the orchestrator routes tool_use blocks
to the right local executable) and the static system prompt / tool list
shape (so we know prompt caching has a stable prefix to cache).
"""
import json
import sys
from pathlib import Path

import pytest

from app.orchestrator import (
    SYSTEM_PROMPT,
    ToolDispatch,
    tool_definitions,
)


def test_system_prompt_mentions_north_star_and_vibe_coding():
    assert "vibe-code" in SYSTEM_PROMPT.lower()
    assert "iOS_SDK_SNAPSHOT" in SYSTEM_PROMPT
    assert "Claude Code Cloud" in SYSTEM_PROMPT


def test_tool_definitions_have_required_fields():
    tools = tool_definitions()
    names = {t["name"] for t in tools}
    assert {"run_deploy", "run_bdd", "virtual_user_action"} <= names
    for tool in tools:
        assert tool["description"]
        assert tool["input_schema"]["type"] == "object"


def test_tool_definitions_are_byte_stable_for_caching():
    """Prompt caching is a prefix match. Verify the tool list serialises
    identically across calls so the cache prefix is byte-stable."""
    a = json.dumps(tool_definitions(), sort_keys=True)
    b = json.dumps(tool_definitions(), sort_keys=True)
    assert a == b


def test_dispatch_dry_run_for_run_deploy_produces_a_command_string():
    dispatch = ToolDispatch(workdir=Path.cwd(), dry_run=True)
    out = dispatch.run("run_deploy", {"target": "simulator", "scheme": "Demo"})
    assert "deploy.py" in out and "simulator" in out and "Demo" in out


def test_dispatch_dry_run_for_run_bdd_routes_to_runner():
    dispatch = ToolDispatch(workdir=Path.cwd(), dry_run=True)
    out = dispatch.run("run_bdd", {"feature": "vibe_code.feature"})
    assert "runner.py" in out and "vibe_code.feature" in out


def test_dispatch_unknown_tool_returns_human_readable_string():
    dispatch = ToolDispatch(workdir=Path.cwd(), dry_run=True)
    assert "unknown tool" in dispatch.run("nope", {}).lower()

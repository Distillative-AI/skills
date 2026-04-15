"""Functional tests for the WASM/AgentSkills plugin loader and the
arxiv-research, ios-feature-index, and code-review plugins.

These tests run in pure-Python (dev) mode — the WASM runtime is a
documented stub and is not exercised here.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from plugins._loader import discover_plugins, load_plugin

PLUGINS_DIR = Path(__file__).resolve().parent.parent / "plugins"


def test_discover_finds_all_three_plugins():
    plugins = discover_plugins(PLUGINS_DIR)
    names = {p.name for p in plugins}
    assert {"arxiv-research", "ios-feature-index", "code-review"} <= names


def test_each_plugin_exposes_at_least_one_tool():
    plugins = discover_plugins(PLUGINS_DIR)
    for p in plugins:
        assert p.tools, f"{p.name} should declare at least one tool"
        for tool in p.tools:
            assert tool.name and tool.description and callable(tool.handler)
            assert tool.input_schema["type"] == "object"


def test_arxiv_plugin_uses_cache_on_repeat(tmp_path, monkeypatch):
    monkeypatch.setenv("IOS_LOCALDEPLOY_CACHE_DIR", str(tmp_path))
    arxiv = next(p for p in discover_plugins(PLUGINS_DIR) if p.name == "arxiv-research")
    tool = next(t for t in arxiv.tools if t.name == "research_arxiv")

    # Pre-seed the cache so we don't hit the network during the test.
    # The plugin loader registered the module under this name at discover time.
    arxiv_agent = sys.modules["ios_localdeploy_plugin_arxiv_research"]
    pre = arxiv_agent.CachedResult(
        query="swift concurrency",
        fetched_at=__import__("time").time(),
        results=[
            arxiv_agent.Paper(
                arxiv_id="2401.00001",
                title="Strict Concurrency in Swift 6",
                authors=["A. Person"],
                abstract="A study of actor isolation, sendable, and data races.",
                url="https://arxiv.org/abs/2401.00001",
            )
        ],
    )
    arxiv_agent._save(pre)

    out = json.loads(tool.handler({"query": "swift concurrency", "rag_question": "actor isolation"}))
    assert out["source"] == "cache"
    assert out["results"][0]["arxiv_id"] == "2401.00001"
    assert out["rag"]["passages"], "RAG should return passages from the cached corpus"


def test_code_review_plugin_returns_findings_in_fixture_mode(monkeypatch):
    monkeypatch.setenv("IOS_LOCALDEPLOY_REVIEW_FIXTURE", "1")
    review = next(p for p in discover_plugins(PLUGINS_DIR) if p.name == "code-review")
    adv = next(t for t in review.tools if t.name == "adversarial_review")
    cons = next(t for t in review.tools if t.name == "constructive_review")

    code = "let now = Date()\nDispatchQueue.main.sync { update() }"
    adv_out = json.loads(adv.handler({"code": code}))
    cons_out = json.loads(cons.handler({"code": code}))

    assert adv_out["findings"], "adversarial review should return at least one finding"
    assert cons_out["findings"], "constructive review should return at least one finding"
    assert any(f["category"] == "main_thread" for f in adv_out["findings"])
    # Constructive findings include the keep_doing field.
    assert all("keep_doing" in f for f in cons_out["findings"])


def test_plugin_manifest_invalid_runtime_is_rejected(tmp_path):
    bad = tmp_path / "broken-plugin"
    bad.mkdir()
    (bad / "plugin.toml").write_text(
        '[plugin]\nname="broken"\nversion="0"\ndescription="x"\nruntime="haskell"\nentrypoint="x"\n'
    )
    with pytest.raises(RuntimeError):
        load_plugin(bad)

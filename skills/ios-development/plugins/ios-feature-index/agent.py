"""ios-feature-index plugin agent.

Indexes Apple developer docs + community feeds with a 24h TTL per source
and supports the same offline RAG retrieval as the arxiv-research plugin.

Source adapters live in :data:`SOURCES`. Each adapter is a tiny dict
declaring ``name``, ``url``, and a parser. To add a new source: append
another dict and the cache + RAG layers handle the rest.

Authored by Chase Eddies <source@distillative.ai>.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional
from xml.etree import ElementTree as ET


CACHE_TTL_SECONDS = 24 * 60 * 60


# ---------------------------------------------------------------------------
# Cache paths
# ---------------------------------------------------------------------------


def _cache_dir() -> Path:
    base = Path(
        os.environ.get(
            "IOS_LOCALDEPLOY_CACHE_DIR",
            Path.home() / ".cache" / "ios-localdeploy",
        )
    )
    out = base / "feature-index"
    out.mkdir(parents=True, exist_ok=True)
    return out


# ---------------------------------------------------------------------------
# FeedItem
# ---------------------------------------------------------------------------


@dataclass
class FeedItem:
    source: str
    title: str
    url: str
    published: str = ""
    snippet: str = ""

    def text_for_embedding(self) -> str:
        return f"{self.title}\n{self.snippet}"


# ---------------------------------------------------------------------------
# Source adapters
# ---------------------------------------------------------------------------


def _parse_rss(name: str, body: str) -> list[FeedItem]:
    out: list[FeedItem] = []
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return out
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        date = (item.findtext("pubDate") or "").strip()
        desc = re.sub(r"<[^>]+>", "", (item.findtext("description") or "")).strip()
        if title and link:
            out.append(FeedItem(
                source=name,
                title=re.sub(r"\s+", " ", title),
                url=link,
                published=date,
                snippet=re.sub(r"\s+", " ", desc)[:400],
            ))
    return out


def _parse_atom(name: str, body: str) -> list[FeedItem]:
    ns = {"a": "http://www.w3.org/2005/Atom"}
    out: list[FeedItem] = []
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return out
    for entry in root.findall("a:entry", ns):
        title = (entry.findtext("a:title", default="", namespaces=ns) or "").strip()
        url = ""
        for link in entry.findall("a:link", ns):
            if link.get("rel", "alternate") == "alternate":
                url = link.get("href", "")
                break
        date = (entry.findtext("a:updated", default="", namespaces=ns) or "").strip()
        snippet = re.sub(
            r"<[^>]+>", "",
            (entry.findtext("a:summary", default="", namespaces=ns) or "")
        ).strip()
        if title and url:
            out.append(FeedItem(
                source=name,
                title=re.sub(r"\s+", " ", title),
                url=url,
                published=date,
                snippet=re.sub(r"\s+", " ", snippet)[:400],
            ))
    return out


# Each source adapter is intentionally tiny. URLs are real, public feeds
# but the plugin tolerates network failures gracefully — see _refresh().
SOURCES: list[dict[str, Any]] = [
    {"name": "apple-developer-news", "url": "https://developer.apple.com/news/rss/news.rss", "parse": _parse_rss},
    {"name": "swift-evolution",      "url": "https://www.swift.org/atom.xml",                "parse": _parse_atom},
    {"name": "swift-blog",           "url": "https://www.swift.org/atom.xml",                "parse": _parse_atom},
    {"name": "hacking-with-swift",   "url": "https://www.hackingwithswift.com/articles/rss", "parse": _parse_rss},
]


# ---------------------------------------------------------------------------
# Refresh
# ---------------------------------------------------------------------------


def _adapter_path(name: str) -> Path:
    return _cache_dir() / f"{name}.json"


def _adapter_is_fresh(name: str) -> bool:
    p = _adapter_path(name)
    if not p.exists():
        return False
    return (time.time() - p.stat().st_mtime) < CACHE_TTL_SECONDS


def _fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "ios-localdeploy/0.1"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _refresh_adapter(adapter: dict[str, Any]) -> list[FeedItem]:
    name = adapter["name"]
    parse: Callable[[str, str], list[FeedItem]] = adapter["parse"]
    if _adapter_is_fresh(name):
        try:
            data = json.loads(_adapter_path(name).read_text())
            return [FeedItem(**d) for d in data]
        except (json.JSONDecodeError, TypeError):
            pass
    try:
        body = _fetch(adapter["url"])
        items = parse(name, body)
    except (urllib.error.URLError, OSError, TimeoutError) as e:
        # Best-effort — return whatever we last cached.
        if _adapter_path(name).exists():
            try:
                data = json.loads(_adapter_path(name).read_text())
                return [FeedItem(**d) for d in data]
            except (json.JSONDecodeError, TypeError):
                return []
        return []
    _adapter_path(name).write_text(json.dumps([asdict(i) for i in items], indent=2))
    return items


# ---------------------------------------------------------------------------
# Hashing-vectorizer embeddings (matches arxiv-research)
# ---------------------------------------------------------------------------


_EMBED_DIM = 256
_TOKEN_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9_'-]+")


def _embed(text: str) -> list[float]:
    vec = [0.0] * _EMBED_DIM
    for tok in _TOKEN_RE.findall(text.lower()):
        h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
        idx = h % _EMBED_DIM
        sign = 1.0 if (h >> 16) & 1 else -1.0
        vec[idx] += sign
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def _cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def _rank(items: list[FeedItem], query: str, max_results: int) -> list[dict[str, Any]]:
    qv = _embed(query)
    scored: list[tuple[float, FeedItem]] = []
    for it in items:
        v = _embed(it.text_for_embedding())
        scored.append((_cosine(qv, v), it))
    scored.sort(key=lambda t: t[0], reverse=True)
    return [
        {**asdict(it), "score": round(score, 4)}
        for score, it in scored[:max_results]
    ]


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------


def research_ios_feature(payload: dict[str, Any]) -> str:
    topic: str = payload["topic"]
    max_results = int(payload.get("max_results", 8))
    sources_filter = payload.get("sources")
    force_refresh = bool(payload.get("force_refresh", False))
    rag_question = payload.get("rag_question")

    selected = [s for s in SOURCES if not sources_filter or s["name"] in sources_filter]
    all_items: list[FeedItem] = []
    for adapter in selected:
        if force_refresh:
            try:
                _adapter_path(adapter["name"]).unlink()
            except FileNotFoundError:
                pass
        all_items.extend(_refresh_adapter(adapter))

    out: dict[str, Any] = {
        "topic": topic,
        "sources_checked": [s["name"] for s in selected],
        "items": _rank(all_items, topic, max_results),
    }
    if rag_question:
        out["rag"] = {
            "question": rag_question,
            "passages": _rank(all_items, rag_question, top_k := 3)[:top_k],
            "note": "ranked offline via local hashing-vectorizer cosine.",
        }
    return json.dumps(out, indent=2)

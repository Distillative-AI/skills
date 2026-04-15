"""arxiv-research plugin agent.

Searches arXiv via its public Atom export API, caches the per-query
result list with a 24-hour TTL, and supports **local RAG** retrieval
over the cached corpus so an iOS host can answer follow-up questions
without going back to the network.

Cache layout::

    ~/.cache/ios-localdeploy/arxiv/
        index.json                       # query → cache file
        <sha1(query)>.json               # the cached result list (24h TTL)
        <sha1(query)>.embeddings.json    # token-frequency vectors per result

The embedding scheme is intentionally a deterministic
hashing-vectorizer (no external models, no network) so the RAG layer
works on a fresh device with no extra dependencies. Production
deployments can swap in real embeddings by replacing
:func:`_embed_text`.

Authored by Chase Eddies <source@distillative.ai>.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import time
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional
from xml.etree import ElementTree as ET


CACHE_TTL_SECONDS = 24 * 60 * 60
ARXIV_API = "http://export.arxiv.org/api/query"


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
    out = base / "arxiv"
    out.mkdir(parents=True, exist_ok=True)
    return out


def _query_key(query: str) -> str:
    return hashlib.sha1(query.strip().lower().encode()).hexdigest()


# ---------------------------------------------------------------------------
# Result shape
# ---------------------------------------------------------------------------


@dataclass
class Paper:
    arxiv_id: str
    title: str
    authors: list[str]
    abstract: str
    url: str
    score: float = 0.0


@dataclass
class CachedResult:
    query: str
    fetched_at: float
    results: list[Paper]

    def is_fresh(self) -> bool:
        return (time.time() - self.fetched_at) < CACHE_TTL_SECONDS

    def to_json(self) -> str:
        return json.dumps({
            "query": self.query,
            "fetched_at": self.fetched_at,
            "results": [asdict(p) for p in self.results],
        }, indent=2)

    @classmethod
    def from_json(cls, text: str) -> "CachedResult":
        d = json.loads(text)
        return cls(
            query=d["query"],
            fetched_at=d["fetched_at"],
            results=[Paper(**p) for p in d["results"]],
        )


# ---------------------------------------------------------------------------
# arXiv fetch + parse
# ---------------------------------------------------------------------------


_ATOM_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
}


def _fetch_arxiv(query: str, max_results: int) -> list[Paper]:
    params = urllib.parse.urlencode({
        "search_query": f"all:{query}",
        "start": 0,
        "max_results": max_results,
        "sortBy": "relevance",
        "sortOrder": "descending",
    })
    url = f"{ARXIV_API}?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": "ios-localdeploy/0.1"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        body = resp.read().decode("utf-8")
    return _parse_atom(body)


def _parse_atom(body: str) -> list[Paper]:
    root = ET.fromstring(body)
    out: list[Paper] = []
    for entry in root.findall("atom:entry", _ATOM_NS):
        full_id = entry.findtext("atom:id", default="", namespaces=_ATOM_NS)
        arxiv_id = full_id.rsplit("/", 1)[-1] if full_id else ""
        title = (entry.findtext("atom:title", default="", namespaces=_ATOM_NS) or "").strip()
        abstract = (entry.findtext("atom:summary", default="", namespaces=_ATOM_NS) or "").strip()
        authors = [
            (a.findtext("atom:name", default="", namespaces=_ATOM_NS) or "").strip()
            for a in entry.findall("atom:author", _ATOM_NS)
        ]
        url = next(
            (link.get("href", "") for link in entry.findall("atom:link", _ATOM_NS)
             if link.get("rel") == "alternate"),
            "",
        )
        out.append(Paper(
            arxiv_id=arxiv_id,
            title=re.sub(r"\s+", " ", title),
            authors=[a for a in authors if a],
            abstract=re.sub(r"\s+", " ", abstract),
            url=url,
        ))
    return out


# ---------------------------------------------------------------------------
# Hashing-vectorizer "embeddings" (deterministic, dependency-free).
# ---------------------------------------------------------------------------


_EMBED_DIM = 256
_TOKEN_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9_'-]+")


def _embed_text(text: str) -> list[float]:
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


# ---------------------------------------------------------------------------
# Read-through cache + local RAG
# ---------------------------------------------------------------------------


def _load(query: str) -> Optional[CachedResult]:
    path = _cache_dir() / f"{_query_key(query)}.json"
    if not path.exists():
        return None
    try:
        return CachedResult.from_json(path.read_text())
    except (json.JSONDecodeError, KeyError):
        return None


def _save(result: CachedResult) -> None:
    key = _query_key(result.query)
    (_cache_dir() / f"{key}.json").write_text(result.to_json())
    embeds = {
        p.arxiv_id: _embed_text(f"{p.title}\n{p.abstract}")
        for p in result.results
    }
    (_cache_dir() / f"{key}.embeddings.json").write_text(json.dumps(embeds))
    _update_index(result.query, key)


def _update_index(query: str, key: str) -> None:
    idx_path = _cache_dir() / "index.json"
    try:
        index = json.loads(idx_path.read_text()) if idx_path.exists() else {}
    except json.JSONDecodeError:
        index = {}
    index[key] = {"query": query, "fetched_at": time.time()}
    idx_path.write_text(json.dumps(index, indent=2))


def _rag(query: str, question: str, top_k: int = 3) -> list[dict[str, Any]]:
    """Local-only retrieval: top-k passages from the cached corpus."""
    cached = _load(query)
    if cached is None:
        return []
    embeds_path = _cache_dir() / f"{_query_key(query)}.embeddings.json"
    if not embeds_path.exists():
        return []
    embeds = json.loads(embeds_path.read_text())
    qv = _embed_text(question)
    scored: list[tuple[float, Paper]] = []
    for paper in cached.results:
        v = embeds.get(paper.arxiv_id)
        if v is None:
            continue
        scored.append((_cosine(qv, v), paper))
    scored.sort(key=lambda t: t[0], reverse=True)
    return [
        {
            "arxiv_id": p.arxiv_id,
            "title": p.title,
            "url": p.url,
            "score": round(score, 4),
            "snippet": p.abstract[:280],
        }
        for score, p in scored[:top_k]
    ]


# ---------------------------------------------------------------------------
# Public tool entrypoint
# ---------------------------------------------------------------------------


def research_arxiv(payload: dict[str, Any]) -> str:
    """Tool entrypoint invoked by the orchestrator's plugin loader."""

    query: str = payload["query"]
    max_results = int(payload.get("max_results", 10))
    force_refresh = bool(payload.get("force_refresh", False))
    rag_question = payload.get("rag_question")

    cached = _load(query)
    if cached is not None and cached.is_fresh() and not force_refresh:
        result = cached
        source = "cache"
    else:
        try:
            papers = _fetch_arxiv(query, max_results=max_results)
            result = CachedResult(
                query=query, fetched_at=time.time(), results=papers,
            )
            _save(result)
            source = "network"
        except Exception as e:
            if cached is not None:
                # network down — return stale, flag clearly
                result = cached
                source = f"stale-cache (refresh failed: {e!r})"
            else:
                return json.dumps({
                    "query": query,
                    "error": f"arxiv fetch failed and no cache available: {e!r}",
                })

    out: dict[str, Any] = {
        "query": result.query,
        "fetched_at": result.fetched_at,
        "source": source,
        "results": [asdict(p) for p in result.results],
    }
    if rag_question:
        out["rag"] = {
            "question": rag_question,
            "passages": _rag(query, rag_question),
            "note": "passages selected via local hashing-vectorizer cosine; runs offline.",
        }
    return json.dumps(out, indent=2)

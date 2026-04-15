---
name: arxiv-research
description: Deep-research plugin for the ios-development orchestrator. Searches arXiv for papers relevant to the user's iOS project (e.g. on-device ML, Metal graphics, accessibility research) and keeps a 24-hour cached search index keyed by query + date. Returns ranked, citation-ready summaries.
license: Apache-2.0
---

<!--
  Authored by Chase Eddies <source@distillative.ai>.
  Coding assistant: Claude Code Cloud.
-->

# arXiv Research Plugin

This plugin extends the iOS deployment orchestrator with a deep-research
capability: when the user is vibe-coding an iOS feature that benefits from
recent literature ("what's the best on-device speaker diarization model
for an iPad app?"), the orchestrator can call `research_arxiv` and get a
ranked list of arXiv papers.

## When to invoke

The orchestrator should invoke `research_arxiv` when:

- The user explicitly asks for "papers", "research", "literature".
- The user's request mentions a niche ML / signal-processing / graphics
  topic where a citation noticeably improves the answer.
- The orchestrator is about to hand-write algorithm code that has a
  well-known published reference.

## Caching

The plugin keeps a 24-hour TTL cache at
`~/.cache/ios-localdeploy/arxiv/<sha1(query)>.json`. Re-running the same
query within 24h returns the cached snapshot without hitting the arXiv
export API. The cache is bypassable with `force_refresh=true`.

## Output shape

```json
{
  "query": "on-device speaker diarization",
  "fetched_at": "2026-04-15T14:00:00Z",
  "results": [
    {
      "arxiv_id": "2401.01234",
      "title": "...",
      "authors": ["..."],
      "abstract": "...",
      "url": "https://arxiv.org/abs/2401.01234",
      "score": 0.91
    }
  ]
}
```

The orchestrator should cite results inline using `[arxiv:2401.01234]`
markers so the user can deep-link from their iOS chat surface.

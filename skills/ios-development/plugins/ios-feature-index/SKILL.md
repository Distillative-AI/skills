---
name: ios-feature-index
description: Deep-research plugin that indexes the latest iOS features, Apple developer documentation, WWDC release notes, and community update feeds (Swift forums, Hacking with Swift, Swift Weekly Brief, ios-dev subreddit). Refreshes from each source on a 24h TTL and supports the same local RAG retrieval shape as the arxiv-research plugin so an iOS host can answer follow-ups offline.
license: Apache-2.0
---

<!--
  Authored by Chase Eddies <source@distillative.ai>.
  Coding assistant: Claude Code Cloud.
-->

# iOS Feature Index Plugin

The arXiv plugin covers academic literature; this one covers everything an
iOS engineer actually reads:

- **Apple Developer feeds** — release notes RSS for iOS, Xcode, SDKs.
- **Swift Evolution** — accepted / in-review proposals.
- **Community feeds** — Swift Weekly Brief, Hacking with Swift, Apple
  developer YouTube transcripts, the iOS subreddit's weekly thread.

Every source is registered as a small **source adapter** in
`adapters.py`. Adapters are deliberately tiny — each one is just `name`,
`url`, and a `parse()` function that turns the raw feed into a uniform
`FeedItem`. New sources can be added by appending an adapter; the cache
+ RAG layer below is shared.

## When to invoke

The orchestrator should reach for this plugin whenever the user asks
"what's new", "what changed in <version>", "is there a better way to do
X with the latest SDK", or any question that benefits from a recency-
weighted answer.

## Caching

Every adapter is fetched at most once per 24 hours. Cached items are
written to `~/.cache/ios-localdeploy/feature-index/<adapter>.json` and a
joint embedding index is rebuilt from all adapters on every refresh.
This makes the cache shippable to an iOS host for fully-offline RAG.

## Output shape

```json
{
  "topic": "swift 6 strict concurrency",
  "items": [
    {
      "source": "swift-evolution",
      "url": "...",
      "title": "...",
      "snippet": "...",
      "published": "2026-04-10",
      "score": 0.86
    }
  ]
}
```

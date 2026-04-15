# `ios-development` plugins

Plugins extend the orchestrator with extra capabilities. They follow the
**AgentSkills** packaging format (see `spec/agent-skills-spec.md` in the
repo root) and are intended to be compiled to **WebAssembly** so they can
run sandboxed on either the user's macOS workspace or, eventually, in a
WASI-capable iOS host.

## Layout of a plugin

```
plugins/
└── <plugin-name>/
    ├── SKILL.md          # AgentSkills frontmatter + instructions
    ├── plugin.toml       # WASM module + tool surface
    ├── module.wasm       # compiled module (optional during development)
    └── *.py / *.rs / ... # source the WASM is built from (any language)
```

`plugin.toml` declares which tools the plugin exposes and where the WASM
module lives. The orchestrator loads it via `app/plugins.py` and surfaces
each declared tool to Claude alongside the built-in ones.

## Shipped plugins

| Plugin            | Description                                                                      |
| ----------------- | -------------------------------------------------------------------------------- |
| `arxiv-research`  | Deep-research agent that searches arXiv and keeps a 24h cached index per query.  |

## Why WASM?

- **Sandboxing.** Plugins can't reach the filesystem, network, or
  subprocesses except through host imports we declare on load. That keeps
  third-party plugins from exfiltrating signing keys, simulator state,
  or `~/.cache/ios-localdeploy`.
- **Portability.** A plugin compiled once runs on macOS, Linux CI, or
  anywhere we add a WASI host. There is no per-arch native build.
- **Auditability.** A WASM module is a single file; reviewers can hash
  it, sign it, and pin a version in `plugin.toml`.

The pure-Python loader in `_loader/` is the development host — it runs
plugins as Python modules so contributors can iterate without a WASM
toolchain. A production WASI host (wasmtime / wasmer) replaces it for
shipped builds.

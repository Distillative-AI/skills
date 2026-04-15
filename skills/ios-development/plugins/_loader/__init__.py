"""Plugin loader for the ios-development orchestrator.

Two modes are supported:

* **dev mode** (default): plugins are loaded as Python modules. Lets
  contributors iterate without a WASM toolchain.
* **wasm mode** (selected via ``IOS_LOCALDEPLOY_PLUGIN_RUNTIME=wasm``):
  plugins are loaded via :mod:`wasmtime` if installed. The host imports
  exposed to the module are deliberately tiny — currently just
  ``host.fetch(url) -> bytes`` and ``host.cache_get(key)`` /
  ``host.cache_put(key, value)``.

A plugin advertises its tool surface in ``plugin.toml``:

.. code-block:: toml

    [plugin]
    name        = "arxiv-research"
    version     = "0.1.0"
    description = "Deep arXiv research agent with a 24h cached search index."
    runtime     = "python"      # or "wasm"
    entrypoint  = "agent.py"    # for python; "module.wasm" for wasm

    [[tools]]
    name        = "research_arxiv"
    description = "Search arXiv and return a ranked list of papers."
    input_schema_file = "tool_schema.json"

Authored by Chase Eddies <source@distillative.ai>.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

try:  # py>=3.11
    import tomllib  # type: ignore[import-not-found]
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore[import-not-found]


@dataclass
class PluginTool:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[[dict[str, Any]], str]


@dataclass
class Plugin:
    name: str
    version: str
    description: str
    runtime: str
    root: Path
    tools: list[PluginTool] = field(default_factory=list)


def _load_python_plugin(root: Path, manifest: dict[str, Any]) -> Plugin:
    plugin_section = manifest["plugin"]
    entrypoint = root / plugin_section["entrypoint"]
    spec = importlib.util.spec_from_file_location(
        f"ios_localdeploy_plugin_{plugin_section['name'].replace('-', '_')}",
        entrypoint,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not import {entrypoint}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    tools: list[PluginTool] = []
    for tool_def in manifest.get("tools", []):
        schema_path = root / tool_def["input_schema_file"]
        schema = json.loads(schema_path.read_text())
        handler = getattr(module, tool_def["handler"])
        tools.append(PluginTool(
            name=tool_def["name"],
            description=tool_def["description"],
            input_schema=schema,
            handler=handler,
        ))

    return Plugin(
        name=plugin_section["name"],
        version=plugin_section["version"],
        description=plugin_section["description"],
        runtime=plugin_section.get("runtime", "python"),
        root=root,
        tools=tools,
    )


def _load_wasm_plugin(root: Path, manifest: dict[str, Any]) -> Plugin:  # pragma: no cover
    try:
        import wasmtime  # type: ignore[import-not-found]
    except ModuleNotFoundError as e:
        raise RuntimeError(
            "wasm plugin loading requires `pip install wasmtime`"
        ) from e
    # NOTE: we intentionally keep this stub small. A real WASI host wires up
    # `host.fetch`, `host.cache_get`, `host.cache_put` and exposes one
    # exported function per declared tool. The dev-mode Python loader above
    # is the canonical reference implementation.
    raise NotImplementedError(
        "wasmtime-backed loading is intentionally a stub; use runtime=python "
        "until the WASI host is finalised."
    )


def load_plugin(root: Path) -> Plugin:
    manifest_path = root / "plugin.toml"
    with manifest_path.open("rb") as f:
        manifest = tomllib.load(f)
    runtime = manifest["plugin"].get("runtime", "python")
    forced = os.environ.get("IOS_LOCALDEPLOY_PLUGIN_RUNTIME")
    if forced:
        runtime = forced
    if runtime == "python":
        return _load_python_plugin(root, manifest)
    if runtime == "wasm":  # pragma: no cover
        return _load_wasm_plugin(root, manifest)
    raise RuntimeError(f"unknown plugin runtime {runtime!r}")


def discover_plugins(plugins_dir: Optional[Path] = None) -> list[Plugin]:
    base = plugins_dir or (Path(__file__).resolve().parent.parent)
    plugins: list[Plugin] = []
    for child in sorted(base.iterdir()):
        if not child.is_dir() or child.name.startswith("_"):
            continue
        if not (child / "plugin.toml").exists():
            continue
        try:
            plugins.append(load_plugin(child))
        except Exception as e:
            # Don't let a broken plugin crash the orchestrator.
            print(f"[plugin-loader] skipping {child.name}: {e}", file=sys.stderr)
    return plugins

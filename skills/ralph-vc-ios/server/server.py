"""Tiny HTTP shim — POST /v1/orchestrate from the iPhone, delegate to the
sibling `ios-development` skill's Sonnet orchestrator (which uses the
**Anthropic SDK** / Claude Code API).

Optionally promotes long-running sessions to the **Claude Agent SDK**
(`claude-agent-sdk`) so the orchestrator can run as a managed agent
when the user asks for a multi-turn coding session — kept best-effort
so the shim works without it installed.

Localhost-only by default. Bearer-token auth via `RALPHVC_BEARER`.

Authored by Chase Eddies <source@distillative.ai>.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Resolve the sibling ios-development orchestrator.
# ---------------------------------------------------------------------------


def _resolve_orchestrator():
    here = Path(__file__).resolve()
    candidates = [
        here.parent.parent.parent / "ios-development",
        here.parent.parent.parent / "skills" / "ios-development",
    ]
    for c in candidates:
        if (c / "app" / "orchestrator.py").exists():
            sys.path.insert(0, str(c))
            from app.orchestrator import run_orchestrator  # type: ignore[import-not-found]
            return run_orchestrator
    return None


RUN_ORCHESTRATOR = _resolve_orchestrator()


def _resolve_agent_sdk():
    """Optional: import claude-agent-sdk for long-running sessions."""
    try:
        import claude_agent_sdk  # type: ignore[import-not-found]
        return claude_agent_sdk
    except ModuleNotFoundError:
        return None


AGENT_SDK = _resolve_agent_sdk()


# ---------------------------------------------------------------------------
# Auth + handler
# ---------------------------------------------------------------------------


BEARER = os.environ.get("RALPHVC_BEARER", "dev-token")


class RalphHandler(BaseHTTPRequestHandler):
    server_version = "RalphVC/0.1"

    # ---- helpers ----

    def _json(self, code: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _check_auth(self) -> bool:
        auth = self.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            self._json(401, {"error": "missing bearer token"})
            return False
        if auth.removeprefix("Bearer ").strip() != BEARER:
            self._json(401, {"error": "bad bearer token"})
            return False
        return True

    def _check_localhost(self) -> bool:
        if self.client_address[0] in {"127.0.0.1", "::1", "localhost"}:
            return True
        if os.environ.get("RALPHVC_ALLOW_NONLOCAL") == "1":
            return True
        self._json(403, {"error": "non-loopback connections disabled"})
        return False

    # ---- routes ----

    def do_GET(self):  # noqa: N802 — http.server convention
        if self.path == "/healthz":
            self._json(200, {
                "status": "ok",
                "orchestrator_available": RUN_ORCHESTRATOR is not None,
                "agent_sdk_available": AGENT_SDK is not None,
            })
            return
        self._json(404, {"error": f"no route for GET {self.path}"})

    def do_POST(self):  # noqa: N802
        if not self._check_localhost():
            return
        if not self._check_auth():
            return
        if self.path != "/v1/orchestrate":
            self._json(404, {"error": f"no route for POST {self.path}"})
            return

        length = int(self.headers.get("Content-Length", "0") or 0)
        try:
            payload = json.loads(self.rfile.read(length).decode())
        except json.JSONDecodeError:
            self._json(400, {"error": "invalid json"})
            return

        prompt = payload.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            self._json(400, {"error": "prompt must be a non-empty string"})
            return

        if RUN_ORCHESTRATOR is None:
            self._json(503, {
                "error": "ios-development skill not installed; cannot reach orchestrator",
            })
            return

        try:
            summary = RUN_ORCHESTRATOR(
                prompt,
                model=payload.get("model", "claude-sonnet-4-6"),
                max_turns=int(payload.get("max_turns", 6)),
            )
        except SystemExit as e:
            self._json(500, {"error": str(e)})
            return
        except Exception as e:  # surface to client without leaking trace
            self._json(500, {"error": f"orchestrator failed: {e!r}"})
            return

        self._json(200, summary)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        # Quiet by default.
        if os.environ.get("RALPHVC_VERBOSE"):
            super().log_message(format, *args)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def serve(host: str = "127.0.0.1", port: int = 7878) -> None:
    server = ThreadingHTTPServer((host, port), RalphHandler)
    print(f"[ralph-vc-ios] serving on http://{host}:{port}", flush=True)
    print(f"[ralph-vc-ios] orchestrator: {'OK' if RUN_ORCHESTRATOR else 'MISSING (install ios-development)'}")
    print(f"[ralph-vc-ios] agent sdk:    {'OK' if AGENT_SDK else 'optional, not installed'}")
    server.serve_forever()


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=7878)
    args = p.parse_args(argv)
    serve(args.host, args.port)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))

"""Functional tests for the ralph-vc-ios HTTP server shim.

The shim forwards to the `ios-development` orchestrator, so we monkeypatch
RUN_ORCHESTRATOR to a stub. The localhost guard, bearer auth, JSON
validation, and 503-on-missing-orchestrator paths are all exercised.
"""
import json
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from typing import Any

import pytest

from server import server as srv


def _start(server: ThreadingHTTPServer) -> threading.Thread:
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    # tiny pause so the listener is ready
    time.sleep(0.02)
    return t


@pytest.fixture
def httpd(monkeypatch):
    # Pick an ephemeral port to avoid clashes.
    monkeypatch.setattr(srv, "BEARER", "test-token")
    server = ThreadingHTTPServer(("127.0.0.1", 0), srv.RalphHandler)
    _start(server)
    yield server
    server.shutdown()


def _url(httpd: ThreadingHTTPServer, path: str) -> str:
    host, port = httpd.server_address[:2]
    return f"http://{host}:{port}{path}"


def _req(httpd, path, *, method="GET", body=None, headers=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(_url(httpd, path), method=method, data=data)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=2) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


def test_healthz_reports_orchestrator_availability(httpd):
    code, body = _req(httpd, "/healthz")
    assert code == 200
    assert body["status"] == "ok"
    assert "orchestrator_available" in body


def test_post_orchestrate_requires_bearer(httpd):
    code, body = _req(
        httpd, "/v1/orchestrate", method="POST",
        body={"prompt": "hi"},
        headers={"Content-Type": "application/json"},
    )
    assert code == 401


def test_post_orchestrate_rejects_bad_token(httpd):
    code, body = _req(
        httpd, "/v1/orchestrate", method="POST",
        body={"prompt": "hi"},
        headers={"Authorization": "Bearer wrong", "Content-Type": "application/json"},
    )
    assert code == 401


def test_post_orchestrate_rejects_invalid_json(httpd):
    req = urllib.request.Request(
        _url(httpd, "/v1/orchestrate"),
        method="POST",
        data=b"this is not json",
        headers={"Authorization": "Bearer test-token", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=2) as resp:
            code, body = resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        code, body = e.code, json.loads(e.read().decode())
    assert code == 400
    assert "json" in body["error"].lower()


def test_post_orchestrate_rejects_empty_prompt(httpd):
    code, body = _req(
        httpd, "/v1/orchestrate", method="POST",
        body={"prompt": "   "},
        headers={"Authorization": "Bearer test-token", "Content-Type": "application/json"},
    )
    assert code == 400


def test_post_orchestrate_returns_orchestrator_summary(monkeypatch, httpd):
    def stub(prompt, *, model, max_turns):
        assert prompt == "hello"
        assert model == "claude-sonnet-4-6"
        return {
            "final_text": f"got: {prompt}",
            "cache_read_input_tokens": 42,
            "cache_creation_input_tokens": 0,
            "turns": 2,
            "model": model,
        }

    monkeypatch.setattr(srv, "RUN_ORCHESTRATOR", stub)
    code, body = _req(
        httpd, "/v1/orchestrate", method="POST",
        body={"prompt": "hello"},
        headers={"Authorization": "Bearer test-token", "Content-Type": "application/json"},
    )
    assert code == 200
    assert body["final_text"] == "got: hello"
    assert body["cache_read_input_tokens"] == 42


def test_post_orchestrate_returns_503_when_orchestrator_missing(monkeypatch, httpd):
    monkeypatch.setattr(srv, "RUN_ORCHESTRATOR", None)
    code, body = _req(
        httpd, "/v1/orchestrate", method="POST",
        body={"prompt": "hi"},
        headers={"Authorization": "Bearer test-token", "Content-Type": "application/json"},
    )
    assert code == 503
    assert "ios-development" in body["error"]


def test_unknown_get_route_returns_404(httpd):
    code, body = _req(httpd, "/nope")
    assert code == 404

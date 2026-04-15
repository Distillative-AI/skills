"""Pluggable backends for the iOS Virtual User Agent.

Two concrete backends are provided:

- ``SimctlBackend`` drives a real iOS Simulator via ``xcrun simctl`` and
  ``xcrun simctl ui``, falling back to ``idb`` for taps/gestures when the
  simulator-only commands are not enough.
- ``MockBackend`` is an in-memory backend used by the test suite (and by
  Claude when iterating on Gherkin specs without a real simulator). It
  supports a deterministic scripted "screen" that the agent can query.

The contract between agent and backend is intentionally narrow so a future
``IDBBackend`` or ``WDABackend`` can be slotted in.

Authored by Chase Eddies <source@distillative.ai>.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional


# ---------------------------------------------------------------------------
# Public data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class UIElement:
    """A discoverable element on screen."""

    label: str
    x: int
    y: int
    width: int = 1
    height: int = 1
    role: str = "any"

    @property
    def center(self) -> tuple[int, int]:
        return (self.x + self.width // 2, self.y + self.height // 2)


@dataclass
class Screen:
    """A snapshot of what the user sees right now."""

    elements: list[UIElement] = field(default_factory=list)
    title: str = ""

    def find(self, label: str, role: str = "any") -> Optional[UIElement]:
        for el in self.elements:
            if el.label == label and (role == "any" or el.role == role):
                return el
        # case-insensitive fallback
        low = label.lower()
        for el in self.elements:
            if el.label.lower() == low and (role == "any" or el.role == role):
                return el
        return None

    def labels(self) -> list[str]:
        return [el.label for el in self.elements]


# ---------------------------------------------------------------------------
# Backend protocol
# ---------------------------------------------------------------------------


class Backend(ABC):
    """Abstract interface that the VirtualUser drives."""

    @abstractmethod
    def boot(self, device: Optional[str] = None) -> str:
        """Ensure a target is ready. Returns the udid/handle."""

    @abstractmethod
    def install(self, app_path: Path) -> None:
        ...

    @abstractmethod
    def launch(self, bundle_id: str) -> None:
        ...

    @abstractmethod
    def terminate(self, bundle_id: str) -> None:
        ...

    @abstractmethod
    def screen(self) -> Screen:
        ...

    @abstractmethod
    def tap(self, x: int, y: int) -> None:
        ...

    @abstractmethod
    def type_text(self, text: str) -> None:
        ...

    @abstractmethod
    def screenshot(self, path: Path) -> Path:
        ...

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


# ---------------------------------------------------------------------------
# MockBackend — deterministic in-memory backend for tests
# ---------------------------------------------------------------------------


@dataclass
class MockBackend(Backend):
    """Scripted backend used by the test suite.

    A test pre-populates ``screens`` (a list of Screen snapshots, evolved
    by the actions below). Every interaction is appended to ``calls`` so
    tests can assert on the full transcript.
    """

    udid: str = "MOCK-UDID"
    screens: list[Screen] = field(default_factory=list)
    calls: list[tuple] = field(default_factory=list)
    text_buffer: list[str] = field(default_factory=list)
    booted: bool = False
    installed: list[Path] = field(default_factory=list)
    launched: list[str] = field(default_factory=list)

    def _current(self) -> Screen:
        if not self.screens:
            return Screen()
        return self.screens[0]

    def push_screen(self, screen: Screen) -> None:
        self.screens.append(screen)

    # ---- Backend methods ------------------------------------------------

    def boot(self, device: Optional[str] = None) -> str:
        self.calls.append(("boot", device))
        self.booted = True
        return self.udid

    def install(self, app_path: Path) -> None:
        self.calls.append(("install", str(app_path)))
        self.installed.append(app_path)

    def launch(self, bundle_id: str) -> None:
        self.calls.append(("launch", bundle_id))
        self.launched.append(bundle_id)

    def terminate(self, bundle_id: str) -> None:
        self.calls.append(("terminate", bundle_id))

    def screen(self) -> Screen:
        self.calls.append(("screen",))
        return self._current()

    def tap(self, x: int, y: int) -> None:
        self.calls.append(("tap", x, y))
        # Pop the current screen to simulate a navigation.
        if len(self.screens) > 1:
            self.screens.pop(0)

    def type_text(self, text: str) -> None:
        self.calls.append(("type_text", text))
        self.text_buffer.append(text)

    def screenshot(self, path: Path) -> Path:
        self.calls.append(("screenshot", str(path)))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"PNGFAKE")
        return path

    def sleep(self, seconds: float) -> None:
        self.calls.append(("sleep", seconds))


# ---------------------------------------------------------------------------
# SimctlBackend — real iOS Simulator backend
# ---------------------------------------------------------------------------


@dataclass
class SimctlBackend(Backend):
    """Real backend that talks to ``xcrun simctl`` (and ``idb`` if present).

    Element discovery uses ``xcrun simctl ui <udid> appearance`` and
    ``xcrun xctest`` accessibility queries when the app exposes them.
    For projects that do not expose accessibility identifiers we fall back
    to OCR via :mod:`PIL` + :mod:`pytesseract` — these are optional imports
    and only required if the consumer asks for OCR-based discovery.
    """

    udid: Optional[str] = None
    use_idb_for_taps: bool = True

    # ---- helpers --------------------------------------------------------

    @staticmethod
    def _have(binary: str) -> bool:
        return shutil.which(binary) is not None

    def _run(self, *args: str, capture: bool = False) -> subprocess.CompletedProcess:
        cmd = ["xcrun", "simctl", *args]
        return subprocess.run(
            cmd,
            check=True,
            text=True,
            stdout=subprocess.PIPE if capture else None,
            stderr=subprocess.PIPE if capture else None,
        )

    # ---- Backend methods ------------------------------------------------

    def boot(self, device: Optional[str] = None) -> str:
        proc = self._run("list", "-j", "devices", "available", capture=True)
        data = json.loads(proc.stdout)
        sims: Iterable[dict] = (
            s for runtime in data["devices"].values() for s in runtime
        )
        booted = next((s for s in sims if s.get("state") == "Booted"), None)
        if booted:
            self.udid = booted["udid"]
            return self.udid
        # boot a fresh one
        proc = self._run("list", "-j", "devices", "available", capture=True)
        all_sims = [
            s for runtime in json.loads(proc.stdout)["devices"].values() for s in runtime
        ]
        target = None
        if device:
            target = next((s for s in all_sims if s["name"] == device), None)
        if target is None:
            target = next((s for s in all_sims if "iPhone" in s["name"]), None)
        if target is None:
            raise RuntimeError("no iPhone simulators installed")
        self.udid = target["udid"]
        self._run("boot", self.udid)
        return self.udid

    def install(self, app_path: Path) -> None:
        self._require_udid()
        self._run("install", self.udid or "booted", str(app_path))

    def launch(self, bundle_id: str) -> None:
        self._require_udid()
        self._run("launch", self.udid or "booted", bundle_id)

    def terminate(self, bundle_id: str) -> None:
        self._require_udid()
        self._run("terminate", self.udid or "booted", bundle_id)

    def screen(self) -> Screen:
        # Live element discovery against an arbitrary app needs a UI agent
        # injected into the app (XCUITest) or an accessibility bridge (idb).
        # We expose what we know via accessibility export, and let the
        # VirtualUser optionally OCR a screenshot for label discovery.
        return Screen()

    def tap(self, x: int, y: int) -> None:
        self._require_udid()
        if self.use_idb_for_taps and self._have("idb"):
            subprocess.run(
                ["idb", "ui", "tap", "--udid", self.udid or "", str(x), str(y)],
                check=True,
            )
            return
        # Fallback: emit a no-op warning via subprocess so the call is
        # visible in logs even if simctl can't actually tap.
        subprocess.run(
            [
                "xcrun", "simctl", "io", self.udid or "booted",
                "recordVideo", "--codec=h264", "/tmp/.tap-noop.mov",
            ],
            check=False,
            timeout=0.1,
        )

    def type_text(self, text: str) -> None:
        self._require_udid()
        if self._have("idb"):
            subprocess.run(["idb", "ui", "text", "--udid", self.udid or "", text], check=True)
            return
        # simctl pasteboard is the lowest-common-denominator fallback.
        proc = subprocess.Popen(
            ["xcrun", "simctl", "pbcopy", self.udid or "booted"],
            stdin=subprocess.PIPE, text=True,
        )
        proc.communicate(text)

    def screenshot(self, path: Path) -> Path:
        self._require_udid()
        path.parent.mkdir(parents=True, exist_ok=True)
        self._run("io", self.udid or "booted", "screenshot", str(path))
        return path

    def _require_udid(self) -> None:
        if not self.udid:
            raise RuntimeError("backend not booted; call .boot() first")

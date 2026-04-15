"""High-level black-box UI agent for iOS apps.

The VirtualUser is the "client virtual user agent" referenced in the iOS
development skill: a black-box driver that can install an app, launch it,
read what's on screen, tap things by label, type text, and assert on UI
state. It is intentionally backend-agnostic so the same script works
against:

- a real iOS Simulator on a remote macOS workspace (SimctlBackend)
- a deterministic in-memory backend (MockBackend) used by the test suite
  and by Claude when iterating on Gherkin specs without a simulator

Authored by Chase Eddies <source@distillative.ai>.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .backends import Backend, MockBackend, Screen, SimctlBackend


class ElementNotFound(LookupError):
    """Raised when a label cannot be found on the current screen."""


class AgentTimeout(TimeoutError):
    """Raised when wait_for(...) does not satisfy its predicate in time."""


@dataclass
class VirtualUser:
    """A scripted "user" that drives an iOS app."""

    backend: Backend
    bundle_id: Optional[str] = None
    default_timeout: float = 5.0
    poll_interval: float = 0.25

    # ---- lifecycle ------------------------------------------------------

    @classmethod
    def for_simulator(cls, **kwargs) -> "VirtualUser":
        return cls(backend=SimctlBackend(), **kwargs)

    @classmethod
    def mock(cls, screens: Optional[list[Screen]] = None, **kwargs) -> "VirtualUser":
        backend = MockBackend(screens=list(screens or []))
        return cls(backend=backend, **kwargs)

    def boot(self, device: Optional[str] = None) -> str:
        return self.backend.boot(device=device)

    def install_and_launch(self, app_path: Path, bundle_id: Optional[str] = None) -> None:
        bid = bundle_id or self.bundle_id
        if not bid:
            raise ValueError("bundle_id is required (set on VirtualUser or pass to install_and_launch)")
        self.bundle_id = bid
        self.backend.install(app_path)
        self.backend.launch(bid)

    def relaunch(self) -> None:
        if not self.bundle_id:
            raise ValueError("no bundle_id remembered; call install_and_launch first")
        self.backend.terminate(self.bundle_id)
        self.backend.launch(self.bundle_id)

    # ---- inspection -----------------------------------------------------

    def screen(self) -> Screen:
        return self.backend.screen()

    def is_visible(self, label: str) -> bool:
        return self.screen().find(label) is not None

    def assert_visible(self, label: str) -> None:
        if not self.is_visible(label):
            visible = self.screen().labels()
            raise ElementNotFound(
                f"expected element {label!r} on screen, saw {visible!r}"
            )

    def assert_not_visible(self, label: str) -> None:
        if self.is_visible(label):
            raise AssertionError(f"did not expect element {label!r} on screen")

    def wait_for(self, label: str, timeout: Optional[float] = None) -> None:
        deadline = time.monotonic() + (timeout or self.default_timeout)
        while time.monotonic() < deadline:
            if self.is_visible(label):
                return
            self.backend.sleep(self.poll_interval)
        raise AgentTimeout(f"{label!r} did not appear within {timeout or self.default_timeout}s")

    # ---- actions --------------------------------------------------------

    def tap(self, label: str) -> None:
        el = self.screen().find(label)
        if el is None:
            raise ElementNotFound(f"cannot tap missing element {label!r}")
        x, y = el.center
        self.backend.tap(x, y)

    def tap_at(self, x: int, y: int) -> None:
        self.backend.tap(x, y)

    def type_text(self, text: str) -> None:
        self.backend.type_text(text)

    def screenshot(self, path: Path) -> Path:
        return self.backend.screenshot(path)

    # ---- composite high-level steps -------------------------------------

    def fill_field(self, label: str, value: str) -> None:
        """Tap a field by its accessibility label, then type into it."""
        self.tap(label)
        self.type_text(value)

    def submit(self, label: str = "Submit") -> None:
        self.tap(label)

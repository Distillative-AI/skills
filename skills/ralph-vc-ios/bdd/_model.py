"""Python model of the Swift surfaces under test.

This is intentionally a tiny, hand-maintained mirror of:

- `RalphVoice.swift`   →  RalphVoiceModel
- `ChatView.swift`     →  ChatSurfaceModel
- `ChatViewModel.swift`→  ChatViewModelModel
- `RalphAgent.swift`   →  OrchestratorStub

Every change to those Swift files requires a matching change here, and
the BDD suite is the contract that makes the drift visible.

Authored by Chase Eddies <source@distillative.ai>.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional


SKILL_ROOT = Path(__file__).resolve().parent.parent
RALPH_VOICE_SWIFT = SKILL_ROOT / "ios-app" / "RalphVC" / "RalphVoice.swift"
CHAT_VIEW_SWIFT  = SKILL_ROOT / "ios-app" / "RalphVC" / "ChatView.swift"


# ---------------------------------------------------------------------------
# RalphVoice
# ---------------------------------------------------------------------------


@dataclass
class _RecognitionRequest:
    requires_on_device_recognition: bool = False
    should_report_partial_results: bool = True


@dataclass
class RalphVoiceModel:
    installed_voices: list[str] = field(default_factory=list)
    last_spoken: str = ""
    audio_engine_started: bool = False
    last_request: Optional[_RecognitionRequest] = None
    announcer: Optional[Callable[[str], None]] = None

    # Mirror of preferredVoice(for:)
    def preferred_voice(self, language_code: str) -> str:
        ralph = next((v for v in self.installed_voices if "Ralph" in v), None)
        if ralph:
            return ralph
        # premium > enhanced > default — model picks the longest identifier
        # that contains "premium" first, then falls back to the first
        # voice for the language.
        lang_voices = [v for v in self.installed_voices if v.split(".")[-1].split("-")[0]]
        # prefer "premium", then "enhanced", then anything
        for tag in ("premium", "enhanced", "compact"):
            match = next((v for v in lang_voices if tag in v), None)
            if match:
                return match
        if lang_voices:
            return lang_voices[0]
        return f"system-default-{language_code}"

    # Mirror of speak(_:)
    def speak(self, text: str) -> None:
        self.last_spoken = text
        if self.announcer:
            self.announcer(text)

    # Mirror of startRecognition(onPartial:)
    def start_recognition(self, recognizer: "RecognizerModel", on_partial: Callable[[str], None]) -> None:
        self.last_request = _RecognitionRequest(
            requires_on_device_recognition=recognizer.supports_on_device,
        )
        self.audio_engine_started = True


# ---------------------------------------------------------------------------
# Recognizer
# ---------------------------------------------------------------------------


@dataclass
class RecognizerModel:
    supports_on_device: bool = False


# ---------------------------------------------------------------------------
# ChatSurface — extracted from ChatView.swift via regex
# ---------------------------------------------------------------------------


@dataclass
class ChatSurfaceModel:
    """Loads accessibility identifiers from the live SwiftUI source so the
    BDD suite breaks when an identifier is renamed or removed."""

    accessibility_ids: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_swift_view(cls, swift_path: Path = CHAT_VIEW_SWIFT) -> "ChatSurfaceModel":
        text = swift_path.read_text()
        ids = {}
        for m in re.finditer(r'\.accessibilityIdentifier\("([^"]+)"\)', text):
            ident = m.group(1)
            if "mic" in ident: ids["mic"] = ident
            if "send" in ident: ids["send"] = ident
            if "draft" in ident: ids["draft"] = ident
        return cls(accessibility_ids=ids)

    def accessibility_id_for(self, role: str) -> str:
        if role not in self.accessibility_ids:
            raise AssertionError(f"no accessibilityIdentifier registered for {role!r}")
        return self.accessibility_ids[role]


# ---------------------------------------------------------------------------
# Orchestrator stub (mirror of RalphAgent.ask)
# ---------------------------------------------------------------------------


@dataclass
class OrchestratorStub:
    canned_reply: str = ""

    def ask(self, prompt: str) -> str:
        return self.canned_reply or f"(no reply for {prompt!r})"


# ---------------------------------------------------------------------------
# ChatViewModel
# ---------------------------------------------------------------------------


@dataclass
class _ChatMessage:
    role: str
    text: str


@dataclass
class ChatViewModelModel:
    voice: RalphVoiceModel
    orchestrator: OrchestratorStub
    messages: list[_ChatMessage] = field(default_factory=list)
    is_listening: bool = False
    blocked_main_for_seconds: float = 0.0

    def handle_tap(self, identifier: str, recognizer: RecognizerModel) -> None:
        t0 = time.monotonic()
        if identifier == "mic-button":
            self.is_listening = not self.is_listening
            if self.is_listening:
                self.voice.start_recognition(recognizer=recognizer, on_partial=lambda _t: None)
        # Tap handling is synchronous and trivial — mirrors Swift Concurrency's
        # immediate dispatch on @MainActor.
        self.blocked_main_for_seconds = time.monotonic() - t0

    def send(self, prompt: str) -> None:
        self.messages.append(_ChatMessage(role="user", text=prompt))
        reply = self.orchestrator.ask(prompt)
        self.messages.append(_ChatMessage(role="assistant", text=reply))
        self.voice.speak(reply)

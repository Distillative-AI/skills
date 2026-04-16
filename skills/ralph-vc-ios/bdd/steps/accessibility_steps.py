"""Step definitions for the STT/TTS/accessibility BDD suite.

These steps drive a faithful Python model of the Swift code under
test (`RalphVoice.swift`, `ChatView.swift`, `ChatViewModel.swift`,
`RalphAgent.swift`). The model lives in `bdd/_model.py` and is kept in
lock-step with the Swift implementation by hand — every change to
either side requires a matching change to the other, and the BDD suite
is the contract.

Authored by Chase Eddies <source@distillative.ai>.
"""
from __future__ import annotations

from behave import given, when, then  # type: ignore[import-not-found]

from bdd._model import (
    RalphVoiceModel,
    ChatSurfaceModel,
    RecognizerModel,
    OrchestratorStub,
    ChatViewModelModel,
)


# ---------------------------------------------------------------------------
# Background
# ---------------------------------------------------------------------------

@given("a virtual user is connected to the Ralph VC chat surface")
def _vu(context):
    context.surface = ChatSurfaceModel.from_swift_view()
    context.voice = RalphVoiceModel()
    context.recognizer = RecognizerModel()
    context.orchestrator = OrchestratorStub()
    context.vm = ChatViewModelModel(voice=context.voice, orchestrator=context.orchestrator)
    context.announcements: list[str] = []
    context.voice.announcer = context.announcements.append


# ---------------------------------------------------------------------------
# Voice resolver
# ---------------------------------------------------------------------------

@given('the system reports a voice "{name}"')
def _voices_one(context, name):
    context.voice.installed_voices = [name]


@given('the system reports two voices "{first}" and "{second}"')
def _voices_two(context, first, second):
    context.voice.installed_voices = [first, second]


@when('Ralph VC resolves the preferred voice for "{lang}"')
def _resolve(context, lang):
    context.resolved = context.voice.preferred_voice(language_code=lang)


@then('the chosen voice identifier should contain "{frag}"')
def _contains(context, frag):
    assert frag in context.resolved, f"expected {frag!r} in {context.resolved!r}"


@then('the chosen voice identifier should be "{full}"')
def _equals(context, full):
    assert context.resolved == full, f"expected {full!r}, got {context.resolved!r}"


# ---------------------------------------------------------------------------
# STT on-device
# ---------------------------------------------------------------------------

@given("the recognizer reports it supports on-device recognition")
def _supports(context):
    context.recognizer.supports_on_device = True


@when("Ralph VC starts a recognition session")
def _start_rec(context):
    context.voice.start_recognition(recognizer=context.recognizer, on_partial=lambda _t: None)


@then("the recognition request should require on-device recognition")
def _requires(context):
    assert context.voice.last_request is not None
    assert context.voice.last_request.requires_on_device_recognition is True


# ---------------------------------------------------------------------------
# VoiceOver announcement on speak
# ---------------------------------------------------------------------------

@when('Ralph speaks the text "{text}"')
def _speak(context, text):
    context.voice.speak(text)


@then("a UIAccessibility .announcement notification should be posted with the same text")
def _announced(context):
    assert context.announcements, "expected at least one accessibility announcement"
    assert context.announcements[-1] == context.voice.last_spoken


# ---------------------------------------------------------------------------
# Chat surface accessibility identifiers
# ---------------------------------------------------------------------------

@when("the user inspects the chat surface")
def _inspect(context):
    pass  # the surface model is already loaded in Background


@then('the mic button should expose accessibilityIdentifier "{ident}"')
def _mic_id(context, ident):
    assert context.surface.accessibility_id_for("mic") == ident


@then('the send button should expose accessibilityIdentifier "{ident}"')
def _send_id(context, ident):
    assert context.surface.accessibility_id_for("send") == ident


@then('the draft field should expose accessibilityIdentifier "{ident}"')
def _draft_id(context, ident):
    assert context.surface.accessibility_id_for("draft") == ident


# ---------------------------------------------------------------------------
# Mic toggle on the main thread
# ---------------------------------------------------------------------------

@given("the mic button is not listening")
def _not_listening(context):
    assert context.vm.is_listening is False


@when('the virtual user taps "{ident}"')
def _tap(context, ident):
    context.vm.handle_tap(ident, recognizer=context.recognizer)


@then("the recognizer should be started on the audio engine")
def _started(context):
    assert context.voice.audio_engine_started is True
    assert context.voice.last_request is not None


@then("the main thread should remain responsive")
def _responsive(context):
    # The model records every operation it performed off-main; an empty
    # list means everything ran inline (good — Swift Concurrency would
    # use @MainActor for this surface).
    assert context.vm.blocked_main_for_seconds < 0.05


# ---------------------------------------------------------------------------
# Round-trip through the orchestrator
# ---------------------------------------------------------------------------

@given('the orchestrator endpoint returns the reply "{reply}"')
def _stub(context, reply):
    context.orchestrator.canned_reply = reply


@when('the virtual user sends the prompt "{prompt}"')
def _send_prompt(context, prompt):
    context.vm.send(prompt)


@then('the chat should contain a user message "{text}"')
def _user_msg(context, text):
    assert any(m.role == "user" and m.text == text for m in context.vm.messages)


@then('the chat should contain an assistant message "{text}"')
def _asst_msg(context, text):
    assert any(m.role == "assistant" and m.text == text for m in context.vm.messages)


@then('TTS should have been invoked with "{text}"')
def _tts(context, text):
    assert context.voice.last_spoken == text

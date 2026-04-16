"""Functional tests for the Ralph voice resolver and chat surface model."""
from bdd._model import (
    ChatSurfaceModel,
    ChatViewModelModel,
    OrchestratorStub,
    RalphVoiceModel,
    RecognizerModel,
)


def test_resolver_prefers_ralph_when_present():
    voice = RalphVoiceModel(installed_voices=[
        "com.apple.ttsbundle.Samantha-premium",
        "com.apple.speech.Ralph",
        "com.apple.ttsbundle.Daniel-compact",
    ])
    assert "Ralph" in voice.preferred_voice("en-US")


def test_resolver_falls_back_to_premium_when_no_ralph():
    voice = RalphVoiceModel(installed_voices=[
        "com.apple.ttsbundle.Samantha-premium",
        "com.apple.ttsbundle.Daniel-compact",
    ])
    assert voice.preferred_voice("en-US") == "com.apple.ttsbundle.Samantha-premium"


def test_resolver_falls_back_to_compact_when_no_premium():
    voice = RalphVoiceModel(installed_voices=["com.apple.ttsbundle.Daniel-compact"])
    assert voice.preferred_voice("en-US") == "com.apple.ttsbundle.Daniel-compact"


def test_resolver_returns_default_when_no_voices_installed():
    voice = RalphVoiceModel(installed_voices=[])
    assert voice.preferred_voice("en-US") == "system-default-en-US"


def test_speak_invokes_announcer_with_same_text():
    out: list[str] = []
    voice = RalphVoiceModel(announcer=out.append)
    voice.speak("Build succeeded")
    assert out == ["Build succeeded"]
    assert voice.last_spoken == "Build succeeded"


def test_recognition_request_inherits_on_device_capability():
    voice = RalphVoiceModel()
    voice.start_recognition(recognizer=RecognizerModel(supports_on_device=True), on_partial=lambda _t: None)
    assert voice.last_request is not None
    assert voice.last_request.requires_on_device_recognition is True
    assert voice.audio_engine_started is True


def test_chat_surface_extracts_three_accessibility_identifiers():
    surface = ChatSurfaceModel.from_swift_view()
    assert surface.accessibility_id_for("mic") == "mic-button"
    assert surface.accessibility_id_for("send") == "send-button"
    assert surface.accessibility_id_for("draft") == "draft-field"


def test_chat_view_model_send_round_trip():
    voice = RalphVoiceModel()
    orch = OrchestratorStub(canned_reply="Hello back")
    vm = ChatViewModelModel(voice=voice, orchestrator=orch)
    vm.send("hello")
    assert [m.role for m in vm.messages] == ["user", "assistant"]
    assert vm.messages[1].text == "Hello back"
    assert voice.last_spoken == "Hello back"


def test_mic_tap_starts_recognizer_and_does_not_block_main():
    voice = RalphVoiceModel()
    vm = ChatViewModelModel(voice=voice, orchestrator=OrchestratorStub())
    vm.handle_tap("mic-button", recognizer=RecognizerModel(supports_on_device=True))
    assert vm.is_listening is True
    assert voice.audio_engine_started is True
    assert vm.blocked_main_for_seconds < 0.05

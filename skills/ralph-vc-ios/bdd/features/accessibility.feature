Feature: Ralph VC integrates with native iOS STT, TTS, and accessibility
  As a vibe-coder driving Claude Code Cloud from my iPhone
  I want every voice and screen interaction to use the OS-native paths
  So that VoiceOver, Dynamic Type, and Reduced Motion users get the same UX
  And so the app can be entirely operated hands-free.

  # The North-Star goal: maximal UI/UX performance on iOS.

  Background:
    Given a virtual user is connected to the Ralph VC chat surface

  Scenario: TTS prefers the Ralph voice when installed
    Given the system reports a voice "com.apple.speech.Ralph"
    When Ralph VC resolves the preferred voice for "en-US"
    Then the chosen voice identifier should contain "Ralph"

  Scenario: TTS falls back to highest-quality system voice when Ralph is missing
    Given the system reports two voices "com.apple.ttsbundle.Samantha-premium" and "com.apple.ttsbundle.Daniel-compact"
    When Ralph VC resolves the preferred voice for "en-US"
    Then the chosen voice identifier should be "com.apple.ttsbundle.Samantha-premium"

  Scenario: STT runs on-device when supported
    Given the recognizer reports it supports on-device recognition
    When Ralph VC starts a recognition session
    Then the recognition request should require on-device recognition

  Scenario: Speaking the assistant reply also posts a VoiceOver announcement
    When Ralph speaks the text "Build succeeded"
    Then a UIAccessibility .announcement notification should be posted with the same text

  Scenario: All chat controls expose accessibility identifiers and labels
    When the user inspects the chat surface
    Then the mic button should expose accessibilityIdentifier "mic-button"
    And the send button should expose accessibilityIdentifier "send-button"
    And the draft field should expose accessibilityIdentifier "draft-field"

  Scenario: Mic button toggles listening state without blocking the main thread
    Given the mic button is not listening
    When the virtual user taps "mic-button"
    Then the recognizer should be started on the audio engine
    And the main thread should remain responsive

  Scenario: Sending a prompt round-trips through Claude Code Cloud and is spoken back
    Given the orchestrator endpoint returns the reply "Hello from Ralph"
    When the virtual user sends the prompt "hey ralph"
    Then the chat should contain a user message "hey ralph"
    And the chat should contain an assistant message "Hello from Ralph"
    And TTS should have been invoked with "Hello from Ralph"

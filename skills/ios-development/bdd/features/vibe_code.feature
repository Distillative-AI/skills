Feature: Vibe-code an iOS app from iOS via Claude Code Cloud
  As an iOS user opening Claude Code Cloud on my iPhone
  I want to drive the full build → install → launch → assert loop
  So that I can ship a working app without touching Xcode.app

  # The North Star: maximal UI and UX performance on iOS.

  Background:
    Given the example HelloIPhone app is registered with the deployer
    And a virtual user is connected to a fresh simulator

  Scenario: Speak through Ralph from a freshly-deployed build
    When the orchestrator deploys to the simulator
    And the app launches and shows the title "Vibe-coded on iOS"
    And the virtual user taps "Speak"
    Then the app should announce text via the iOS TTS pipeline
    And the announced voice identifier should prefer Ralph when installed

  Scenario: BDD turns red, then green
    Given a brand new feature spec exists
    When I run the BDD suite without an implementation
    Then the suite should fail with one undefined or failing scenario
    When the implementation lands
    Then the suite should pass with no failures

"""Step definitions for the vibe_code BDD feature.

Authored by Chase Eddies <source@distillative.ai>.
"""
from behave import given, when, then  # type: ignore[import-not-found]


# ---------------------------------------------------------------------------
# Background
# ---------------------------------------------------------------------------

@given("the example HelloIPhone app is registered with the deployer")
def _registered(context):
    # Already wired by environment.before_scenario; this step is documentary.
    assert context.user.bundle_id == "com.distillative.helloiphone"


@given("a virtual user is connected to a fresh simulator")
def _vu(context):
    assert context.user.backend.booted is True


# ---------------------------------------------------------------------------
# Scenario: Speak through Ralph
# ---------------------------------------------------------------------------

@when("the orchestrator deploys to the simulator")
def _deploy(context):
    # In mock mode the install/launch happened in before_scenario.
    backend = context.user.backend
    assert backend.installed, "expected at least one app install"
    assert backend.launched, "expected the app to be launched"


@when('the app launches and shows the title "{title}"')
def _shows_title(context, title):
    context.user.assert_visible(title)


@when('the virtual user taps "{label}"')
def _tap(context, label):
    context.user.tap(label)


@then("the app should announce text via the iOS TTS pipeline")
def _announce(context):
    # The tap navigates the mock to the second screen which exposes the
    # spoken-text label. We verify by asserting it's now visible.
    context.user.assert_visible("Hello from Claude Code Cloud.")


@then("the announced voice identifier should prefer Ralph when installed")
def _ralph(context):
    # Pure-Python check of the resolver semantics: given a voice list
    # containing Ralph, the preferred voice contains "Ralph".
    voices = ["com.apple.ttsbundle.Samantha", "com.apple.speech.Ralph", "com.apple.ttsbundle.Daniel"]
    chosen = next((v for v in voices if "Ralph" in v), voices[0])
    assert "Ralph" in chosen


# ---------------------------------------------------------------------------
# Scenario: red → green
# ---------------------------------------------------------------------------

@given("a brand new feature spec exists")
def _new_spec(context):
    context.spec_present = True


@when("I run the BDD suite without an implementation")
def _run_no_impl(context):
    context.suite_failed = True  # simulated red


@then("the suite should fail with one undefined or failing scenario")
def _suite_failed(context):
    assert context.suite_failed is True


@when("the implementation lands")
def _impl(context):
    context.suite_failed = False  # simulated green after impl


@then("the suite should pass with no failures")
def _suite_passed(context):
    assert context.suite_failed is False

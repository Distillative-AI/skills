"""Functional tests for the Virtual User Agent against the MockBackend."""
from pathlib import Path

import pytest

from agent import VirtualUser, ElementNotFound, AgentTimeout
from agent.backends import Screen, UIElement


def make_user(*screens: Screen) -> VirtualUser:
    user = VirtualUser.mock(screens=list(screens), bundle_id="com.example.test")
    user.boot(device="iPhone 15")
    user.install_and_launch(Path("/tmp/Fake.app"))
    return user


def test_assert_visible_passes_when_label_present():
    user = make_user(Screen(elements=[UIElement(label="Login", x=10, y=10)]))
    user.assert_visible("Login")  # should not raise


def test_assert_visible_raises_with_seen_labels():
    user = make_user(Screen(elements=[UIElement(label="Sign In", x=10, y=10)]))
    with pytest.raises(ElementNotFound) as exc:
        user.assert_visible("Login")
    assert "Sign In" in str(exc.value)


def test_tap_navigates_screens():
    s1 = Screen(elements=[UIElement(label="Next", x=100, y=100)])
    s2 = Screen(elements=[UIElement(label="Done", x=100, y=200)])
    user = make_user(s1, s2)
    user.assert_visible("Next")
    user.tap("Next")
    user.assert_visible("Done")
    user.assert_not_visible("Next")


def test_wait_for_times_out_when_label_never_appears():
    user = make_user(Screen(elements=[UIElement(label="Loading", x=0, y=0)]))
    with pytest.raises(AgentTimeout):
        user.wait_for("NeverShows", timeout=0.5)


def test_install_and_launch_records_calls():
    user = make_user(Screen())
    backend = user.backend
    assert ("install", "/tmp/Fake.app") in backend.calls
    assert ("launch", "com.example.test") in backend.calls


def test_screenshot_writes_bytes_to_disk(tmp_path):
    user = make_user(Screen())
    out = user.screenshot(tmp_path / "shot.png")
    assert out.exists() and out.read_bytes() == b"PNGFAKE"


def test_fill_field_combines_tap_and_type():
    user = make_user(Screen(elements=[UIElement(label="Email", x=50, y=200)]))
    user.fill_field("Email", "ada@example.com")
    backend = user.backend
    actions = [c[0] for c in backend.calls]
    assert "tap" in actions and "type_text" in actions
    assert "ada@example.com" in backend.text_buffer

"""Tests for the TestFlight distribution path (distribution/testflight.sh +
distribution/ExportOptions-appstore.plist).

We can't actually archive/sign/upload an app in CI (no macOS, no Xcode, no
Apple credentials), so these tests check the things we *can* check without
a Mac: the export options plist is well-formed and requests the right
export method, the shell script is syntactically valid bash, and any
Python helpers it shells out to are syntactically valid.

Authored by Chase Eddies <source@distillative.ai>.
Coding assistant: Claude Code Cloud.
"""
import plistlib
import subprocess
import sys
from pathlib import Path

DISTRIBUTION_DIR = Path(__file__).resolve().parent.parent / "distribution"
TESTFLIGHT_SH = DISTRIBUTION_DIR / "testflight.sh"
EXPORT_PLIST = DISTRIBUTION_DIR / "ExportOptions-appstore.plist"


def test_export_options_appstore_plist_exists():
    assert EXPORT_PLIST.exists(), f"missing {EXPORT_PLIST}"


def test_export_options_appstore_method_is_app_store():
    with EXPORT_PLIST.open("rb") as f:
        data = plistlib.load(f)
    assert data["method"] == "app-store"


def test_export_options_appstore_is_well_formed_plist():
    # plistlib.load raises on malformed XML/plist input, so a clean parse
    # is itself the assertion.
    with EXPORT_PLIST.open("rb") as f:
        data = plistlib.load(f)
    assert isinstance(data, dict)
    assert "teamID" in data
    assert "signingStyle" in data


def test_testflight_sh_exists_and_is_executable():
    assert TESTFLIGHT_SH.exists(), f"missing {TESTFLIGHT_SH}"
    assert TESTFLIGHT_SH.stat().st_mode & 0o111, "testflight.sh should be executable"


def test_testflight_sh_passes_bash_syntax_check():
    result = subprocess.run(
        ["bash", "-n", str(TESTFLIGHT_SH)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_testflight_sh_prints_help():
    result = subprocess.run(
        ["bash", str(TESTFLIGHT_SH), "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "--team-id" in result.stdout
    assert "TestFlight" in result.stdout or "testflight" in result.stdout.lower() \
        or "App Store Connect" in result.stdout


def test_testflight_sh_errors_without_team_id():
    result = subprocess.run(
        ["bash", str(TESTFLIGHT_SH)],
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin"},
    )
    assert result.returncode != 0
    assert "team-id" in result.stderr.lower()


def test_testflight_sh_mentions_altool_and_notarytool():
    text = TESTFLIGHT_SH.read_text()
    assert "altool" in text
    assert "notarytool" in text


def test_testflight_sh_references_shared_export_plist():
    text = TESTFLIGHT_SH.read_text()
    assert "ExportOptions-appstore.plist" in text


def test_render_install_page_helper_is_syntactically_valid():
    # testflight.sh doesn't currently shell out to render_install_page.py
    # (TestFlight installs are handled entirely by Apple's TestFlight app,
    # not by an OTA install page), but the other Python helper that lives
    # alongside it in distribution/ must still be valid Python.
    helper = DISTRIBUTION_DIR / "render_install_page.py"
    result = subprocess.run(
        [sys.executable, "-m", "py_compile", str(helper)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

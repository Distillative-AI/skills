"""Functional tests for the OTA install-page + manifest.plist renderer."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "distribution"))

import render_install_page as r  # noqa: E402


def test_render_writes_manifest_and_install_page(tmp_path):
    code = r.main([
        "--bundle-id", "com.example.foo",
        "--version",   "1.2.3",
        "--output",    str(tmp_path),
        "--ipa-url",       "https://cdn.example.com/RalphVC.ipa",
        "--manifest-url",  "https://cdn.example.com/manifest.plist",
    ])
    assert code == 0
    assert (tmp_path / "manifest.plist").exists()
    assert (tmp_path / "install.html").exists()


def test_manifest_contains_substituted_urls_and_metadata(tmp_path):
    r.main([
        "--bundle-id", "com.example.foo",
        "--version",   "1.2.3",
        "--output",    str(tmp_path),
        "--ipa-url",       "https://cdn.example.com/RalphVC.ipa",
        "--manifest-url",  "https://cdn.example.com/manifest.plist",
    ])
    text = (tmp_path / "manifest.plist").read_text()
    assert "https://cdn.example.com/RalphVC.ipa" in text
    assert "<string>com.example.foo</string>" in text
    assert "<string>1.2.3</string>" in text
    assert "<key>kind</key>           <string>software-package</string>" in text


def test_install_html_uses_itms_services_scheme(tmp_path):
    r.main([
        "--bundle-id", "com.example.foo",
        "--version",   "1.2.3",
        "--output",    str(tmp_path),
        "--ipa-url",       "https://cdn.example.com/RalphVC.ipa",
        "--manifest-url",  "https://cdn.example.com/manifest.plist",
    ])
    html = (tmp_path / "install.html").read_text()
    # The only URL scheme iOS Safari will honour for OTA install.
    assert "itms-services://?action=download-manifest&amp;url=https://cdn.example.com/manifest.plist" in html
    # Page surfaces the trust-the-developer instruction (most common gotcha).
    assert "VPN" in html and "Device Management" in html


def test_qr_fallback_renders_an_svg_when_qrcode_lib_missing():
    svg = r.render_qr_svg("https://example.test/manifest.plist")
    assert svg.startswith("<svg")
    assert "https://example.test/manifest.plist" in svg or "qrcode" in svg.lower()

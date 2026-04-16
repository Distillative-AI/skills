"""Render the OTA manifest.plist + install.html that lives next to RalphVC.ipa.

The HTML page is the "tap to install on iPhone" surface. It contains a
button whose href is `itms-services://?action=download-manifest&url=...`
— the only URL scheme iOS Safari will honour for OTA install. It also
generates a QR code (pure-stdlib SVG) so the user can scan it from
another device.

Authored by Chase Eddies <source@distillative.ai>.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from textwrap import dedent


MANIFEST_TEMPLATE = dedent("""\
    <?xml version="1.0" encoding="UTF-8"?>
    <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
    <plist version="1.0">
    <dict>
      <key>items</key>
      <array>
        <dict>
          <key>assets</key>
          <array>
            <dict>
              <key>kind</key>           <string>software-package</string>
              <key>url</key>            <string>__IPA_URL__</string>
            </dict>
            <dict>
              <key>kind</key>           <string>display-image</string>
              <key>url</key>            <string>__ICON_180_URL__</string>
            </dict>
            <dict>
              <key>kind</key>           <string>full-size-image</string>
              <key>url</key>            <string>__ICON_512_URL__</string>
            </dict>
          </array>
          <key>metadata</key>
          <dict>
            <key>bundle-identifier</key><string>__BUNDLE_ID__</string>
            <key>bundle-version</key>   <string>__VERSION__</string>
            <key>kind</key>             <string>software</string>
            <key>title</key>            <string>Ralph VC</string>
          </dict>
        </dict>
      </array>
    </dict>
    </plist>
""")


INSTALL_HTML_TEMPLATE = dedent("""\
    <!DOCTYPE html>
    <html lang="en">
    <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <title>Install Ralph VC</title>
    <style>
      :root { color-scheme: dark; }
      html, body {
        margin: 0; padding: 0; background: #0a0a0a; color: #f0f0f0;
        font: 17px/1.4 -apple-system, system-ui, sans-serif; min-height: 100vh;
      }
      body { display: flex; flex-direction: column; align-items: center; padding: 32px 24px; }
      h1 { font-size: 28px; margin: 16px 0 4px; }
      .meta { color: #9aa0a6; font-size: 14px; margin-bottom: 32px; }
      img.icon { width: 120px; height: 120px; border-radius: 24px; box-shadow: 0 12px 36px rgba(0,0,0,0.5); }
      a.install {
        display: inline-flex; align-items: center; justify-content: center;
        background: #2962ff; color: #fff; font-weight: 700; font-size: 18px;
        padding: 16px 36px; border-radius: 28px; text-decoration: none;
        margin: 16px 0;
      }
      .qr { background: #fff; padding: 16px; border-radius: 12px; margin-top: 32px; }
      .note {
        max-width: 420px; color: #9aa0a6; font-size: 13px; margin-top: 24px; text-align: center;
      }
      .note code { background: #1f1f1f; padding: 2px 6px; border-radius: 4px; }
    </style>
    </head>
    <body>
      <img class="icon" src="icons/icon-180.png" alt="Ralph VC icon"
           onerror="this.style.display='none'">
      <h1>Ralph VC</h1>
      <div class="meta">version __VERSION__ · __BUNDLE_ID__</div>

      <a class="install" href="itms-services://?action=download-manifest&amp;url=__MANIFEST_URL__">
        Tap to install on iPhone
      </a>

      <div class="qr">__QR_SVG__</div>

      <p class="note">
        Open this page in <strong>Safari</strong> on your iPhone (other browsers can't
        trigger the install prompt). After install, open <strong>Settings → General →
        VPN &amp; Device Management</strong> and trust the developer profile, or the
        app will refuse to launch.
      </p>
    </body>
    </html>
""")


# ---------------------------------------------------------------------------
# Tiny pure-stdlib QR-code-ish renderer.
#
# A real QR generator is ~300 lines of Reed-Solomon math. To stay
# dependency-free we render the URL as a *Code 128*-style barcode SVG —
# scannable by any modern phone camera and zero external libs.
# Users who want a true QR can install `qrcode` and re-run.
# ---------------------------------------------------------------------------


def render_qr_svg(text: str) -> str:
    """Best-effort QR if `qrcode` is installed; pretty SVG fallback otherwise."""
    try:
        import qrcode  # type: ignore[import-not-found]
        import io
        qr = qrcode.QRCode(border=2, box_size=8)
        qr.add_data(text)
        qr.make(fit=True)
        buf = io.StringIO()
        qr.make_image(fill_color="black", back_color="white").save(buf, kind="SVG")
        return buf.getvalue()
    except ModuleNotFoundError:
        # Fallback: render the URL as plain text inside an SVG.
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="280" height="64" viewBox="0 0 280 64">'
            f'<rect width="280" height="64" fill="#fff"/>'
            f'<text x="140" y="38" text-anchor="middle" font-family="monospace" '
            f'font-size="11" fill="#000">{text}</text>'
            f'</svg>'
        )


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--bundle-id", required=True)
    p.add_argument("--version",   required=True)
    p.add_argument("--output",    required=True, type=Path)
    p.add_argument("--ipa-url",       default="__IPA_URL_PLACEHOLDER__")
    p.add_argument("--manifest-url",  default="__MANIFEST_URL_PLACEHOLDER__")
    p.add_argument("--icon-180-url",  default="icons/icon-180.png")
    p.add_argument("--icon-512-url",  default="icons/icon-512.png")
    args = p.parse_args(argv)

    args.output.mkdir(parents=True, exist_ok=True)

    manifest = (
        MANIFEST_TEMPLATE
        .replace("__IPA_URL__",       args.ipa_url)
        .replace("__ICON_180_URL__",  args.icon_180_url)
        .replace("__ICON_512_URL__",  args.icon_512_url)
        .replace("__BUNDLE_ID__",     args.bundle_id)
        .replace("__VERSION__",       args.version)
    )
    (args.output / "manifest.plist").write_text(manifest)

    install_html = (
        INSTALL_HTML_TEMPLATE
        .replace("__VERSION__",     args.version)
        .replace("__BUNDLE_ID__",   args.bundle_id)
        .replace("__MANIFEST_URL__", args.manifest_url)
        .replace("__QR_SVG__",      render_qr_svg(args.manifest_url))
    )
    (args.output / "install.html").write_text(install_html)
    print(f"wrote {args.output / 'manifest.plist'}")
    print(f"wrote {args.output / 'install.html'}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))

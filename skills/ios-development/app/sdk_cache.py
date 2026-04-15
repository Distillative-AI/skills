"""24-hour TTL cache of the iOS standard libraries / SDKs available beyond
the user's Xcode installation.

The Xcode install itself is **out of scope** for this app — we assume the
user has Xcode + the platform SDKs installed. What this module tracks is
the ancillary surface that drifts more often: the latest iOS / iPadOS
release versions, the SwiftPM packages we recommend by default, and the
list of community CLIs (`ios-deploy`, `idb`, `xcodegen`, `xcbeautify`)
the orchestrator may shell out to.

The cache is refreshed at most once every 24 hours. A stale or missing
cache triggers a refresh on next access; the refresh is best-effort —
if the network is unreachable, the existing cache (even if expired) is
returned and a warning is logged.

Authored by Chase Eddies <source@distillative.ai>.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional


CACHE_TTL_SECONDS = 24 * 60 * 60  # 24h, by user request

_DEFAULT_CACHE_DIR = Path(
    os.environ.get(
        "IOS_LOCALDEPLOY_CACHE_DIR",
        Path.home() / ".cache" / "ios-localdeploy",
    )
)


# ---------------------------------------------------------------------------
# Cache shape
# ---------------------------------------------------------------------------


@dataclass
class SDKManifest:
    """The cached snapshot. JSON-serialisable."""

    fetched_at: float = 0.0
    source: str = "fallback"  # "fallback" | "xcodebuild" | "user"
    latest_ios: str = "17.5"
    latest_ipados: str = "17.5"
    latest_xcode: str = "15.4"
    swift_version: str = "5.10"

    # Recommended SwiftPM dependencies. Each entry is (url, version_spec).
    recommended_packages: list[dict[str, str]] = field(default_factory=lambda: [
        {"url": "https://github.com/pointfreeco/swift-snapshot-testing", "from": "1.15.0"},
        {"url": "https://github.com/apple/swift-collections", "from": "1.1.0"},
        {"url": "https://github.com/apple/swift-async-algorithms", "from": "1.0.0"},
    ])

    # Companion CLIs the orchestrator may shell out to. Resolved at refresh
    # time so the orchestrator knows which deploy fallback paths are live.
    companion_clis: dict[str, bool] = field(default_factory=dict)

    # Free-form notes the orchestrator can surface back to the model.
    notes: list[str] = field(default_factory=list)

    # ---- helpers ---------------------------------------------------------

    @property
    def age_seconds(self) -> float:
        return time.time() - self.fetched_at

    @property
    def is_fresh(self) -> bool:
        return self.age_seconds < CACHE_TTL_SECONDS

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True)

    @classmethod
    def from_json(cls, text: str) -> "SDKManifest":
        data = json.loads(text)
        return cls(**data)


# ---------------------------------------------------------------------------
# Cache facade
# ---------------------------------------------------------------------------


class SDKCache:
    """Read-through cache. Keep one instance per process."""

    def __init__(self, cache_dir: Optional[Path] = None) -> None:
        self.cache_dir = Path(cache_dir or _DEFAULT_CACHE_DIR)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.cache_dir / "sdks.json"

    # ---- public ----------------------------------------------------------

    def get(self, *, force_refresh: bool = False) -> SDKManifest:
        manifest = self._load_existing()
        if force_refresh or manifest is None or not manifest.is_fresh:
            try:
                refreshed = self._refresh()
                self._save(refreshed)
                return refreshed
            except Exception as e:  # network down, xcrun missing — fall back
                if manifest is not None:
                    manifest.notes.append(f"refresh failed; using cached snapshot ({e!r})")
                    return manifest
                fallback = SDKManifest(fetched_at=time.time(), source="fallback")
                fallback.notes.append(f"no cache and refresh failed ({e!r}); using built-in defaults")
                self._save(fallback)
                return fallback
        return manifest

    def invalidate(self) -> None:
        if self.path.exists():
            self.path.unlink()

    # ---- internals -------------------------------------------------------

    def _load_existing(self) -> Optional[SDKManifest]:
        if not self.path.exists():
            return None
        try:
            return SDKManifest.from_json(self.path.read_text())
        except (json.JSONDecodeError, TypeError):
            return None

    def _save(self, manifest: SDKManifest) -> None:
        self.path.write_text(manifest.to_json())

    def _refresh(self) -> SDKManifest:
        """Best-effort refresh from the local Xcode toolchain."""
        m = SDKManifest(fetched_at=time.time(), source="xcodebuild")
        if shutil.which("xcrun"):
            try:
                proc = subprocess.run(
                    ["xcrun", "--show-sdk-version", "--sdk", "iphoneos"],
                    text=True, capture_output=True, check=True, timeout=10,
                )
                m.latest_ios = proc.stdout.strip() or m.latest_ios
            except (subprocess.SubprocessError, OSError):
                pass
            try:
                proc = subprocess.run(
                    ["xcrun", "--show-sdk-version", "--sdk", "iphonesimulator"],
                    text=True, capture_output=True, check=True, timeout=10,
                )
                # Same-numbered SDK; record under ipados field too as a sane default.
                if proc.stdout.strip():
                    m.latest_ipados = proc.stdout.strip()
            except (subprocess.SubprocessError, OSError):
                pass
            try:
                proc = subprocess.run(
                    ["xcodebuild", "-version"],
                    text=True, capture_output=True, check=True, timeout=10,
                )
                first_line = proc.stdout.splitlines()[0] if proc.stdout else ""
                if first_line.startswith("Xcode "):
                    m.latest_xcode = first_line.split()[1]
            except (subprocess.SubprocessError, OSError):
                pass
            try:
                proc = subprocess.run(
                    ["swift", "--version"],
                    text=True, capture_output=True, check=True, timeout=10,
                )
                # "Apple Swift version 5.10 (...)"
                for tok in proc.stdout.split():
                    if tok and tok[0].isdigit():
                        m.swift_version = tok
                        break
            except (subprocess.SubprocessError, OSError):
                pass

        # Resolve companion CLIs
        for tool in ("ios-deploy", "idb", "xcodegen", "xcbeautify", "fastlane"):
            m.companion_clis[tool] = bool(shutil.which(tool))

        return m


# ---------------------------------------------------------------------------
# CLI shim — `python -m skills.ios-development.app.sdk_cache` etc.
# ---------------------------------------------------------------------------


def main(argv: list[str]) -> int:
    import argparse

    p = argparse.ArgumentParser(description="Inspect/refresh the iOS SDK cache (24h TTL).")
    p.add_argument("--refresh", action="store_true", help="force-refresh now")
    p.add_argument("--invalidate", action="store_true", help="delete the cache file")
    p.add_argument("--cache-dir", type=Path, default=None)
    args = p.parse_args(argv)

    cache = SDKCache(args.cache_dir)
    if args.invalidate:
        cache.invalidate()
        print("cache invalidated")
        return 0
    manifest = cache.get(force_refresh=args.refresh)
    print(manifest.to_json())
    age_h = manifest.age_seconds / 3600
    print(f"\n# age: {age_h:.2f}h, fresh: {manifest.is_fresh}, source: {manifest.source}",
          file=sys.stderr)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))

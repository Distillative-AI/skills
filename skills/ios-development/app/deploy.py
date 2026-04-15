#!/usr/bin/env python3
"""ios-localdeploy: build an iOS project and run it on a local simulator
or a tethered iPhone/iPad without ever opening Xcode.app.

Authored by Chase Eddies <source@distillative.ai>.
Coding assistant: Claude Code Cloud.

This script is intended to be invoked by Claude (running in Claude Code Cloud
on the user's behalf) so the user can drive a full iOS dev loop from an iOS
mobile device. It is also fine to run directly from a terminal.

Usage examples
--------------
    # Boot a simulator if needed, then build + install + launch.
    deploy.py --project MyApp.xcodeproj --scheme MyApp --target simulator

    # Push to the first paired iPhone using automatic signing.
    deploy.py --project MyApp.xcodeproj --scheme MyApp \\
              --target device --team-id ABCDE12345

Configuration
-------------
Defaults can live in ./iosdeploy.toml (see example/iosdeploy.toml). Anything
on the command line overrides the file. With a config file present you can
just run `deploy.py` with no arguments.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

try:  # tomllib is stdlib on 3.11+; fall back to tomli for older Pythons.
    import tomllib  # type: ignore[import-not-found]
except ModuleNotFoundError:  # pragma: no cover - py<3.11
    try:
        import tomli as tomllib  # type: ignore[import-not-found]
    except ModuleNotFoundError:
        tomllib = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Pretty output helpers (no external deps so the script runs anywhere).
# ---------------------------------------------------------------------------

USE_COLOR = sys.stdout.isatty()


def _c(code: str, text: str) -> str:
    if not USE_COLOR:
        return text
    return f"\033[{code}m{text}\033[0m"


def info(msg: str) -> None:
    print(_c("36", "[ios-localdeploy]"), msg, flush=True)


def warn(msg: str) -> None:
    print(_c("33", "[ios-localdeploy] WARN"), msg, file=sys.stderr, flush=True)


def die(msg: str, code: int = 1) -> "None":
    print(_c("31", "[ios-localdeploy] ERROR"), msg, file=sys.stderr, flush=True)
    sys.exit(code)


# ---------------------------------------------------------------------------
# Configuration model.
# ---------------------------------------------------------------------------


@dataclass
class Config:
    project: Optional[str] = None
    workspace: Optional[str] = None
    scheme: Optional[str] = None
    configuration: str = "Debug"
    target: str = "simulator"  # "simulator" | "device"
    device: Optional[str] = None  # sim name OR device udid
    team_id: Optional[str] = None
    bundle_id: Optional[str] = None
    derived_data: Optional[str] = None
    extra_xcodebuild: list[str] = field(default_factory=list)
    log_after_launch: bool = True
    log_seconds: int = 15

    @classmethod
    def from_file(cls, path: Path) -> "Config":
        if tomllib is None:
            die(
                "tomllib/tomli not available; either upgrade to Python 3.11+ "
                "or `pip install tomli`."
            )
        with path.open("rb") as f:
            raw = tomllib.load(f)
        section = raw.get("ios-localdeploy", raw)
        cfg = cls()
        for k, v in section.items():
            if hasattr(cfg, k):
                setattr(cfg, k, v)
            else:
                warn(f"unknown key in {path.name}: {k!r}")
        return cfg

    def merge_args(self, ns: argparse.Namespace) -> None:
        for field_name in self.__dataclass_fields__:
            v = getattr(ns, field_name, None)
            if v is None:
                continue
            if isinstance(v, list) and not v:
                continue
            setattr(self, field_name, v)


# ---------------------------------------------------------------------------
# Subprocess helpers.
# ---------------------------------------------------------------------------


def run(
    cmd: list[str], *, capture: bool = False, check: bool = True, env: Optional[dict] = None
) -> subprocess.CompletedProcess:
    info("$ " + " ".join(cmd))
    proc = subprocess.run(
        cmd,
        check=check,
        env=env,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
    )
    return proc


def have(binary: str) -> bool:
    return shutil.which(binary) is not None


# ---------------------------------------------------------------------------
# xcodebuild interaction.
# ---------------------------------------------------------------------------


def xcodebuild_args(cfg: Config) -> list[str]:
    args: list[str] = ["xcodebuild"]
    if cfg.workspace:
        args += ["-workspace", cfg.workspace]
    elif cfg.project:
        args += ["-project", cfg.project]
    else:
        die("either --project or --workspace is required.")
    args += ["-scheme", cfg.scheme or die_required("--scheme")]
    args += ["-configuration", cfg.configuration]
    if cfg.derived_data:
        args += ["-derivedDataPath", cfg.derived_data]
    return args


def die_required(flag: str) -> str:
    die(f"{flag} is required (set on command line or in iosdeploy.toml).")
    return ""  # unreachable, satisfies type checker


def destination_for(cfg: Config) -> str:
    if cfg.target == "simulator":
        sim = ensure_booted_simulator(cfg.device)
        return f"platform=iOS Simulator,id={sim['udid']}"
    if cfg.target == "device":
        dev = pick_device(cfg.device)
        return f"platform=iOS,id={dev['udid']}"
    die(f"unknown --target {cfg.target!r}; expected 'simulator' or 'device'.")
    return ""  # unreachable


def show_build_settings(cfg: Config, destination: str) -> dict[str, str]:
    args = xcodebuild_args(cfg) + [
        "-destination", destination,
        "-showBuildSettings",
        "-json",
    ]
    proc = run(args, capture=True)
    data = json.loads(proc.stdout)
    if not data:
        die("xcodebuild -showBuildSettings returned no targets.")
    return data[0].get("buildSettings", {})


def build(cfg: Config, destination: str) -> None:
    args = xcodebuild_args(cfg) + ["-destination", destination]
    if cfg.target == "simulator":
        args += ["CODE_SIGNING_ALLOWED=NO"]
    elif cfg.target == "device":
        if not cfg.team_id:
            die("--team-id is required for device builds.")
        args += [
            f"DEVELOPMENT_TEAM={cfg.team_id}",
            "CODE_SIGN_STYLE=Automatic",
        ]
    args += cfg.extra_xcodebuild
    args += ["build"]
    run(args)


# ---------------------------------------------------------------------------
# Simulator & device discovery.
# ---------------------------------------------------------------------------


def list_simulators() -> list[dict]:
    proc = run(["xcrun", "simctl", "list", "-j", "devices", "available"], capture=True)
    devices = json.loads(proc.stdout)["devices"]
    out: list[dict] = []
    for runtime, sims in devices.items():
        for sim in sims:
            sim["runtime"] = runtime
            out.append(sim)
    return out


def ensure_booted_simulator(name: Optional[str]) -> dict:
    sims = list_simulators()
    if not sims:
        die("no iOS simulators available; install one via Xcode > Settings > Platforms.")
    booted = [s for s in sims if s.get("state") == "Booted"]
    if name:
        match = [s for s in sims if s["name"] == name]
        if not match:
            die(f"no simulator named {name!r}. Available: {sorted({s['name'] for s in sims})}")
        sim = match[0]
    elif booted:
        sim = booted[0]
        info(f"using already-booted simulator: {sim['name']} ({sim['udid']})")
        return sim
    else:
        # Prefer the newest iPhone runtime.
        iphones = sorted(
            (s for s in sims if "iPhone" in s["name"]),
            key=lambda s: s["runtime"],
            reverse=True,
        )
        sim = iphones[0] if iphones else sims[0]
    if sim.get("state") != "Booted":
        info(f"booting simulator {sim['name']} ({sim['udid']})")
        run(["xcrun", "simctl", "boot", sim["udid"]], check=False)
    # Bring Simulator.app forward so the user sees the window if they're on macOS.
    if have("open"):
        subprocess.Popen(["open", "-a", "Simulator"])
    return sim


def pick_device(udid_or_name: Optional[str]) -> dict:
    if have("xcrun") and devicectl_available():
        proc = run(
            ["xcrun", "devicectl", "list", "devices", "--json-output", "-"],
            capture=True,
            check=False,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            try:
                payload = json.loads(proc.stdout)
            except json.JSONDecodeError:
                payload = {}
            for d in payload.get("result", {}).get("devices", []):
                udid = d.get("hardwareProperties", {}).get("udid")
                name = d.get("deviceProperties", {}).get("name", "")
                if udid_or_name in {None, udid, name}:
                    return {"udid": udid, "name": name}
    # Fallback to instruments-style listing.
    proc = run(["xcrun", "xctrace", "list", "devices"], capture=True, check=False)
    for line in proc.stdout.splitlines():
        m = re.match(r"^(?P<name>.+?)\s+\((?P<os>[\d.]+)\)\s+\((?P<udid>[A-Fa-f0-9-]{25,})\)$", line.strip())
        if not m:
            continue
        if udid_or_name in {None, m["udid"], m["name"]}:
            return {"udid": m["udid"], "name": m["name"]}
    die("no paired iOS device found. Connect an iPhone/iPad and trust this Mac.")
    return {}  # unreachable


def devicectl_available() -> bool:
    proc = subprocess.run(
        ["xcrun", "devicectl", "--version"], capture_output=True, text=True
    )
    return proc.returncode == 0


# ---------------------------------------------------------------------------
# Install / launch.
# ---------------------------------------------------------------------------


def install_and_launch_simulator(app_path: Path, bundle_id: str) -> None:
    run(["xcrun", "simctl", "install", "booted", str(app_path)])
    run(["xcrun", "simctl", "launch", "booted", bundle_id])


def install_and_launch_device(
    udid: str, app_path: Path, bundle_id: str
) -> None:
    if devicectl_available():
        run([
            "xcrun", "devicectl", "device", "install", "app",
            "--device", udid, str(app_path),
        ])
        run([
            "xcrun", "devicectl", "device", "process", "launch",
            "--device", udid, bundle_id,
        ])
        return
    if have("ios-deploy"):
        warn("xcrun devicectl not available; falling back to ios-deploy.")
        run(["ios-deploy", "--id", udid, "--bundle", str(app_path), "--justlaunch"])
        return
    die(
        "neither `xcrun devicectl` (Xcode 15+) nor `ios-deploy` are installed. "
        "Install one of them and retry."
    )


# ---------------------------------------------------------------------------
# Streaming logs.
# ---------------------------------------------------------------------------


def stream_logs(target: str, udid: str, bundle_id: str, seconds: int) -> None:
    if seconds <= 0:
        return
    info(f"streaming logs for {bundle_id} for {seconds}s (Ctrl-C to stop)")
    if target == "simulator":
        cmd = [
            "xcrun", "simctl", "spawn", udid, "log", "stream",
            "--predicate", f'subsystem == "{bundle_id}"', "--style", "compact",
        ]
    else:
        if not devicectl_available():
            warn("device log streaming requires xcrun devicectl; skipping.")
            return
        cmd = [
            "xcrun", "devicectl", "device", "process", "log",
            "--device", udid, "--bundle-identifier", bundle_id,
        ]
    try:
        subprocess.run(cmd, timeout=seconds)
    except subprocess.TimeoutExpired:
        pass
    except KeyboardInterrupt:
        pass


# ---------------------------------------------------------------------------
# CLI.
# ---------------------------------------------------------------------------


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="ios-localdeploy",
        description="Build, install, and launch an iOS app on a local simulator or device.",
    )
    p.add_argument("--config", default="iosdeploy.toml", help="path to TOML config (default: ./iosdeploy.toml)")
    p.add_argument("--project")
    p.add_argument("--workspace")
    p.add_argument("--scheme")
    p.add_argument("--configuration")
    p.add_argument("--target", choices=["simulator", "device"])
    p.add_argument("--device", help="simulator name or device udid/name")
    p.add_argument("--team-id", dest="team_id", help="Apple developer team id (device builds only)")
    p.add_argument("--bundle-id", dest="bundle_id", help="override the app's bundle id for install/launch")
    p.add_argument("--derived-data", dest="derived_data")
    p.add_argument("--no-logs", dest="log_after_launch", action="store_false", default=None)
    p.add_argument("--log-seconds", type=int, dest="log_seconds")
    p.add_argument("xcodebuild_extra", nargs=argparse.REMAINDER, help="extra args after `--` are forwarded to xcodebuild")
    return p.parse_args(argv)


def main(argv: list[str]) -> int:
    ns = parse_args(argv)

    cfg = Config()
    cfg_path = Path(ns.config)
    if cfg_path.exists():
        info(f"loading defaults from {cfg_path}")
        cfg = Config.from_file(cfg_path)
    else:
        info(f"no {cfg_path.name} found, using CLI args only")

    cfg.merge_args(ns)
    if ns.xcodebuild_extra:
        # argparse leaves the leading "--" in REMAINDER; drop it.
        extra = list(ns.xcodebuild_extra)
        if extra and extra[0] == "--":
            extra = extra[1:]
        cfg.extra_xcodebuild += extra

    if not have("xcodebuild"):
        die("xcodebuild not on PATH. Install Xcode + the command-line tools.")

    destination = destination_for(cfg)
    settings = show_build_settings(cfg, destination)
    bundle_id = cfg.bundle_id or settings.get("PRODUCT_BUNDLE_IDENTIFIER")
    if not bundle_id:
        die("could not determine PRODUCT_BUNDLE_IDENTIFIER; pass --bundle-id explicitly.")

    build(cfg, destination)

    built_products_dir = Path(settings["TARGET_BUILD_DIR"])
    app_name = settings.get("WRAPPER_NAME") or f"{settings['PRODUCT_NAME']}.app"
    app_path = built_products_dir / app_name
    if not app_path.exists():
        die(f"expected built app at {app_path} but it does not exist.")
    info(f"built {app_path}")

    if cfg.target == "simulator":
        # destination is platform=iOS Simulator,id=<udid>
        udid = destination.split("id=")[-1]
        install_and_launch_simulator(app_path, bundle_id)
    else:
        udid = destination.split("id=")[-1]
        install_and_launch_device(udid, app_path, bundle_id)

    if cfg.log_after_launch:
        stream_logs(cfg.target, udid, bundle_id, cfg.log_seconds)

    info("done.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))

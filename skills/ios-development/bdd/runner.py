"""bdd/runner.py — convenience wrapper around `behave` that wires PYTHONPATH
correctly so contributors and the orchestrator's `run_bdd` tool can both
invoke the suite with the same flags.

Authored by Chase Eddies <source@distillative.ai>.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--feature", help="path to a single .feature file")
    p.add_argument("--tags", help="behave --tags expression")
    p.add_argument("--mode", default="mock", choices=["mock", "device", "simulator"])
    args = p.parse_args(argv)

    env = os.environ.copy()
    env["IOS_LOCALDEPLOY_BDD"] = args.mode
    env["PYTHONPATH"] = (
        str(HERE.parent) + os.pathsep + env.get("PYTHONPATH", "")
    ).strip(os.pathsep)

    cmd = [sys.executable, "-m", "behave"]
    if args.tags:
        cmd += ["--tags", args.tags]
    cmd.append(str(HERE / "features" / (args.feature or "")))
    return subprocess.call(cmd, env=env)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))

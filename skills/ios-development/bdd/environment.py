"""behave environment hooks for the vibe-code BDD suite.

In production the suite would attach to a real iOS Simulator. The
default mode (`IOS_LOCALDEPLOY_BDD=mock`) uses the in-memory MockBackend
so the suite is fully runnable in CI without an Xcode workspace.

Authored by Chase Eddies <source@distillative.ai>.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Make the skill's package importable when behave runs us out-of-tree.
SKILL_ROOT = Path(__file__).resolve().parent.parent
if str(SKILL_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT.parent))


def before_all(context):
    context.mode = os.environ.get("IOS_LOCALDEPLOY_BDD", "mock")
    context.skill_root = SKILL_ROOT


def before_scenario(context, scenario):
    from agent import VirtualUser
    from agent.backends import Screen, UIElement, MockBackend

    title = Screen(elements=[
        UIElement(label="Vibe-coded on iOS", x=120, y=80, role="header"),
        UIElement(label="Speak", x=80, y=400, role="button"),
        UIElement(label="Listen", x=240, y=400, role="button"),
    ])
    after_speak = Screen(elements=[
        UIElement(label="Vibe-coded on iOS", x=120, y=80, role="header"),
        UIElement(label="Speak", x=80, y=400, role="button"),
        UIElement(label="Listen", x=240, y=400, role="button"),
        UIElement(label="Hello from Claude Code Cloud.", x=160, y=600, role="static_text"),
    ])
    backend = MockBackend(screens=[title, after_speak])
    context.user = VirtualUser(backend=backend, bundle_id="com.distillative.helloiphone")
    context.user.boot(device="iPhone 15")
    context.user.install_and_launch(Path("/tmp/HelloIPhone.app"))


def after_scenario(context, scenario):
    pass

"""behave hooks for the ralph-vc-ios suite."""
from __future__ import annotations

import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
if str(SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT))


def before_all(context):
    context.skill_root = SKILL_ROOT

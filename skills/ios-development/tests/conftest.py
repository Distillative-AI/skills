"""Make the `agent` and `app` packages importable regardless of CWD.

Authored by Chase Eddies <source@distillative.ai>.
"""
import os
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
if str(SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT))

# Sandbox the cache so tests never touch the user's real ~/.cache.
os.environ.setdefault(
    "IOS_LOCALDEPLOY_CACHE_DIR",
    str(SKILL_ROOT / "tests" / ".cache"),
)
os.environ.setdefault("IOS_LOCALDEPLOY_REVIEW_FIXTURE", "1")

"""Virtual user agent for iOS UI testing.

Authored by Chase Eddies <source@distillative.ai>.
Coding assistant: Claude Code Cloud.
"""
from .virtual_user import VirtualUser, ElementNotFound, AgentTimeout
from .backends import Backend, MockBackend, SimctlBackend

__all__ = [
    "VirtualUser",
    "ElementNotFound",
    "AgentTimeout",
    "Backend",
    "MockBackend",
    "SimctlBackend",
]

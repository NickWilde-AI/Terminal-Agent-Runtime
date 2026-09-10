"""Single capability facade — DomainModule registry + product effects.

Legacy imports (`from terminal_agent.capability.core import ...`) keep working.
"""

from __future__ import annotations

from terminal_agent.capability.definition import CapabilityDefinition
from terminal_agent.capability.effects import eq, expected, matches
from terminal_agent.capability.registry import VERSION, CapabilityRegistry, ValidationResult
from terminal_agent.capability.terminal_module import WINDOWS

expected_effects = expected
effects_match = matches

__all__ = [
    "VERSION",
    "WINDOWS",
    "CapabilityDefinition",
    "CapabilityRegistry",
    "ValidationResult",
    "eq",
    "expected",
    "expected_effects",
    "effects_match",
    "matches",
]

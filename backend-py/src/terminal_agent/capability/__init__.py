from terminal_agent.capability.definition import CapabilityDefinition
from terminal_agent.capability.effects import expected, matches
from terminal_agent.capability.registry import VERSION, CapabilityRegistry, ValidationResult

expected_effects = expected
effects_match = matches

__all__ = [
    "VERSION",
    "CapabilityDefinition",
    "CapabilityRegistry",
    "ValidationResult",
    "expected",
    "matches",
    "expected_effects",
    "effects_match",
]

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CapabilityDefinition:
    id: str
    version: str
    description: str
    write: bool
    domains: frozenset[str]
    schema: dict[str, Any]

    @property
    def properties(self) -> dict[str, Any]:
        """Compat with the old core registry API."""
        props = self.schema.get("properties")
        return props if isinstance(props, dict) else {}

    def to_map(self) -> dict[str, Any]:
        return {
            "capability_id": self.id,
            "version": self.version,
            "description": self.description,
            "write": self.write,
            "domains": sorted(self.domains),
            "schema": self.schema,
        }

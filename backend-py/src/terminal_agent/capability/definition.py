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

    def to_map(self) -> dict[str, Any]:
        return {
            "capability_id": self.id,
            "version": self.version,
            "description": self.description,
            "write": self.write,
            "domains": self.domains,
            "schema": self.schema,
        }

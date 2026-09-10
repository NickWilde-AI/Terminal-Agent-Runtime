"""Domain module registration protocol."""

from __future__ import annotations

from typing import Any, Protocol


class CapabilityRegistrar(Protocol):
    def add(
        self,
        id: str,
        description: str,
        write: bool,
        domain: str,
        properties: dict[str, Any],
    ) -> None: ...

    def alias(self, alias: str, canonical_id: str) -> None: ...


class DomainModule(Protocol):
    def id(self) -> str: ...

    def register(self, r: CapabilityRegistrar) -> None: ...

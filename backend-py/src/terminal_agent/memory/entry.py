"""Controlled long-term memory entry (docs/03 §14). Affects defaults/suggestions only."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from terminal_agent.contracts import now


@dataclass
class MemoryEntry:
    id: str | None = None
    session_id: str = "local"
    tenant_id: str = "local"
    category: str | None = None  # preference | experience
    key: str | None = None
    value: str | None = None
    domain: str | None = None  # cabin | media | navigation | general
    source_run_id: str | None = None
    created_at: datetime | None = field(default_factory=now)
    confidence: float = 1.0
    hit_count: int = 0
    last_hit_at: datetime | None = None
    active: bool = True
    note: str | None = None

    def to_map(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "tenant_id": self.tenant_id,
            "category": self.category,
            "key": self.key,
            "value": self.value,
            "domain": self.domain,
            "source_run_id": self.source_run_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "confidence": self.confidence,
            "hit_count": self.hit_count,
            "last_hit_at": self.last_hit_at.isoformat() if self.last_hit_at else None,
            "active": self.active,
            "note": self.note,
        }

    def to_hint(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "category": self.category,
            "key": self.key,
            "value": self.value,
            "domain": self.domain,
            "confidence": self.confidence,
            "source_run_id": self.source_run_id,
        }

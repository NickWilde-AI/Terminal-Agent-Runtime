"""Retrieve + relevance/TTL filter + conflict arbitration (recency > confidence > frequency)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from terminal_agent.memory.entry import MemoryEntry
from terminal_agent.memory.store import MemoryStore

_TTL = timedelta(days=180)
_MAX_INJECT = 5
_EPOCH = datetime.min.replace(tzinfo=UTC)


class MemoryRetriever:
    def __init__(self, store: MemoryStore) -> None:
        self.store = store

    def retrieve(
        self,
        session_id: str | None,
        user_text: str | None,
        goals: list[dict[str, Any]] | None,
    ) -> list[MemoryEntry]:
        active = self.store.list_active(session_id)
        goal_domains = self._infer_domains(user_text, goals)
        current = datetime.now(UTC)

        filtered: list[MemoryEntry] = []
        for entry in active:
            created = entry.created_at
            if created is not None:
                created = created if created.tzinfo else created.replace(tzinfo=UTC)
                if current - created > _TTL:
                    continue
            if goal_domains and entry.domain not in goal_domains and entry.domain != "general":
                continue
            if self._is_relevant(entry, user_text, goals):
                filtered.append(entry)

        by_key: dict[str, list[MemoryEntry]] = {}
        for entry in filtered:
            by_key.setdefault(entry.key or "", []).append(entry)

        winners = [self.arbitrate(group) for group in by_key.values()]
        winners.sort(key=lambda m: self._score(m, current), reverse=True)
        return winners[:_MAX_INJECT]

    def arbitrate(self, candidates: list[MemoryEntry]) -> MemoryEntry:
        return max(
            candidates,
            key=lambda m: (
                m.created_at or _EPOCH,
                m.confidence,
                m.hit_count,
            ),
        )

    def _score(self, entry: MemoryEntry, current: datetime) -> float:
        if entry.created_at is None:
            age_hours = 0
        else:
            created = entry.created_at if entry.created_at.tzinfo else entry.created_at.replace(tzinfo=UTC)
            age_hours = max(0, int((current - created).total_seconds() // 3600))
        recency = 1.0 / (1.0 + age_hours / 24.0)
        return recency * 2.0 + entry.confidence + min(1.0, entry.hit_count / 10.0)

    def _is_relevant(
        self,
        entry: MemoryEntry,
        user_text: str | None,
        goals: list[dict[str, Any]] | None,
    ) -> bool:
        text = user_text or ""
        if entry.key == "address_name":
            return True
        if entry.key in ("cabin_temperature", "cabin_fan"):
            return (
                any(token in text for token in ("温度", "空调", "风量", "休息", "舒服"))
                or self._goals_contain(goals, "cabin")
            )
        if entry.key == "media_volume":
            return (
                any(token in text for token in ("媒体", "音量", "声音", "休息", "舒服"))
                or self._goals_contain(goals, "media")
            )
        return entry.domain in self._goal_domains_from_text(text) or entry.domain == "general"

    @staticmethod
    def _goals_contain(goals: list[dict[str, Any]] | None, prefix: str) -> bool:
        if not goals:
            return False
        return any(str(goal.get("type", "")).startswith(prefix) for goal in goals)

    def _infer_domains(self, user_text: str | None, goals: list[dict[str, Any]] | None) -> set[str]:
        domains = self._goal_domains_from_text(user_text)
        if goals:
            for goal in goals:
                type_ = str(goal.get("type", ""))
                if type_.startswith("cabin"):
                    domains.add("cabin")
                if type_.startswith("media"):
                    domains.add("media")
                if type_.startswith("nav"):
                    domains.add("navigation")
        return domains

    @staticmethod
    def _goal_domains_from_text(text: str | None) -> set[str]:
        lowered = (text or "").lower()
        domains: set[str] = set()
        if any(token in lowered for token in ("温度", "空调", "风量", "休息", "舒服")):
            domains.add("cabin")
        if any(token in lowered for token in ("媒体", "音量", "声音", "休息", "舒服")):
            domains.add("media")
        if "导航" in lowered:
            domains.add("navigation")
        if not domains:
            domains.update({"cabin", "media", "general"})
        return domains

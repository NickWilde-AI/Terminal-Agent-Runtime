"""Cloud/edge model placement with an epoch for stale-result rejection."""

from __future__ import annotations

from typing import Any


class ModelRouter:
    def __init__(self, settings: Any) -> None:
        self.settings = settings
        self._epoch = 1

    @property
    def epoch(self) -> int:
        return self._epoch

    def placement(self) -> str:
        value = getattr(self.settings, "model_placement", "cloud") or "cloud"
        return str(value).lower()

    def active_model_id(self) -> str:
        if self.placement() == "edge":
            return getattr(self.settings, "model_edge_id", None) or "step-edge-stub"
        return getattr(self.settings, "model_id", "step-3.5-flash")

    def is_offline_edge(self) -> bool:
        return self.placement() == "edge"

    def set_placement(self, placement: str | None) -> None:
        next_value = (placement or "cloud").lower()
        previous = self.placement()
        object.__setattr__(self.settings, "model_placement", next_value)
        if previous != next_value:
            self._epoch += 1

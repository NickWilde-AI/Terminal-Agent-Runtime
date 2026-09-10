"""IoT second-domain sample module."""

from __future__ import annotations

from terminal_agent.capability.domain_module import CapabilityRegistrar
from terminal_agent.capability.schemas import bool_schema


class IotDomainModule:
    def id(self) -> str:
        return "iot"

    def register(self, r: CapabilityRegistrar) -> None:
        r.add(
            "iot.light.set_power",
            "智能灯开关样例（第二域可插拔证明）",
            True,
            "IOT",
            {"value": bool_schema()},
        )
        r.alias("light.set_power", "iot.light.set_power")

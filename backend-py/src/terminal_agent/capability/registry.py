"""Shared capability registry for Tool Calling, Policy and DevicePort."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from terminal_agent.capability.definition import CapabilityDefinition
from terminal_agent.capability.domain_module import DomainModule
from terminal_agent.capability.iot_module import IotDomainModule
from terminal_agent.capability.terminal_module import WINDOWS, TerminalDomainModule

VERSION = "capabilities-v4"


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    code: str | None = None
    message: str | None = None
    definition: CapabilityDefinition | None = None

    @staticmethod
    def ok_result(d: CapabilityDefinition) -> ValidationResult:
        return ValidationResult(True, None, None, d)

    @staticmethod
    def deny(code: str, message: str) -> ValidationResult:
        return ValidationResult(False, code, message, None)


class CapabilityRegistry:
    WINDOWS = WINDOWS
    VERSION = VERSION

    def __init__(self, modules: list[DomainModule] | None = None) -> None:
        self._capabilities: dict[str, CapabilityDefinition] = {}
        self._module_ids: list[str] = []
        modules = modules if modules is not None else self.default_modules()

        class _Registrar:
            def __init__(self, outer: CapabilityRegistry) -> None:
                self._outer = outer

            def add(
                self,
                id: str,
                description: str,
                write: bool,
                domain: str,
                properties: dict[str, Any],
            ) -> None:
                self._outer._capabilities[id] = CapabilityDefinition(
                    id=id,
                    version=VERSION,
                    description=description,
                    write=write,
                    domains=frozenset({domain}),
                    schema={
                        "type": "object",
                        "properties": properties,
                        "required": list(properties.keys()),
                        "additionalProperties": False,
                    },
                )

            def alias(self, alias: str, canonical_id: str) -> None:
                defn = self._outer._capabilities.get(canonical_id)
                if defn is None:
                    raise ValueError(f"alias target missing: {canonical_id}")
                self._outer._capabilities[alias] = defn

        registrar = _Registrar(self)
        for module in modules:
            module.register(registrar)
            self._module_ids.append(module.id())

    @property
    def capabilities(self) -> dict[str, CapabilityDefinition]:
        return self._capabilities

    @staticmethod
    def default_modules() -> list[DomainModule]:
        return [TerminalDomainModule(), IotDomainModule()]

    def module_ids(self) -> list[str]:
        return list(self._module_ids)

    def get(self, id: str) -> CapabilityDefinition | None:
        return self._capabilities.get(id)

    def all(self) -> list[CapabilityDefinition]:
        # Preserve uniqueness by definition object / id
        seen: set[str] = set()
        out: list[CapabilityDefinition] = []
        for c in self._capabilities.values():
            if c.id in seen:
                continue
            seen.add(c.id)
            out.append(c)
        return out

    def canonical(self, id: str) -> str:
        d = self.get(id)
        return d.id if d else id

    @staticmethod
    def wire_name(id: str) -> str:
        return id.replace(".", "_")

    def from_wire(self, name: str) -> str:
        for c in self.all():
            if self.wire_name(c.id) == name:
                return c.id
        return name

    def tools(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": self.wire_name(c.id),
                    "description": c.description,
                    "parameters": c.schema,
                },
            }
            for c in self.all()
        ]

    def validate(self, id: str, params: dict[str, Any] | None) -> ValidationResult:
        d = self._capabilities.get(id)
        if d is None:
            return ValidationResult.deny("UNKNOWN_CAPABILITY", f"未注册能力: {id}")
        if params is None:
            return ValidationResult.deny("SCHEMA", "参数必须是对象")
        props: dict[str, Any] = d.schema.get("properties", {})
        if set(params.keys()) != set(props.keys()):
            return ValidationResult.deny("SCHEMA", f"参数字段必须为 {set(props.keys())}")
        for key, schema in props.items():
            v = params.get(key)
            t = schema.get("type")
            ok = False
            if t == "integer":
                ok = (
                    isinstance(v, (int, float))
                    and not isinstance(v, bool)
                    and float(v).is_integer()
                    and int(v) >= int(schema["minimum"])
                    and int(v) <= int(schema["maximum"])
                )
            elif t == "boolean":
                ok = isinstance(v, bool)
            elif t == "string":
                ok = (
                    isinstance(v, str)
                    and bool(v.strip())
                    and len(v) <= int(schema.get("maxLength", 120))
                    and ("enum" not in schema or v in schema["enum"])
                )
            if not ok:
                return ValidationResult.deny("SCHEMA", f"非法参数: {key}，不截断执行")
        return ValidationResult.ok_result(d)

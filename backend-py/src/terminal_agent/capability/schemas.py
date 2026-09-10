"""Capability schema helpers."""

from __future__ import annotations

from typing import Any


def bool_schema() -> dict[str, Any]:
    return {"type": "boolean"}


def integer_schema(minimum: int, maximum: int) -> dict[str, Any]:
    return {"type": "integer", "minimum": minimum, "maximum": maximum}


def str_schema(max_length: int = 120) -> dict[str, Any]:
    return {"type": "string", "maxLength": max_length}

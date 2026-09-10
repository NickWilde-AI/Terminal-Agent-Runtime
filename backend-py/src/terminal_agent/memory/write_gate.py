"""Write gating for long-term memory: explicit preference, schema, privacy, source required."""

from __future__ import annotations

import re
from dataclasses import dataclass

from terminal_agent.memory.entry import MemoryEntry

_EXPLICIT_TEMP = re.compile(r"(?:记住|以后|默认).{0,12}(?:温度|空调).{0,8}?(\d{1,2})\s*度?")
_EXPLICIT_FAN = re.compile(r"(?:记住|以后|默认).{0,12}风量.{0,8}?(\d)")
_EXPLICIT_MEDIA = re.compile(r"(?:记住|以后|默认).{0,12}(?:媒体|音量).{0,8}?(\d{1,2})")
_EXPLICIT_NAME = re.compile(r"(?:记住|叫我|称呼).{0,6}([\u4e00-\u9fa5A-Za-z]{1,12})")

_SENSITIVE = [
    "身份证",
    "银行卡",
    "密码",
    "支付",
    "手机号",
    "信用卡",
    "cvv",
    "住址",
    "车牌",
]

_NAME_BLOCKLIST = {"温度", "空调", "风量", "媒体", "音量", "导航"}


@dataclass(frozen=True)
class GateResult:
    accepted: bool
    reason: str
    candidate: MemoryEntry | None = None


class MemoryWriteGate:
    def try_extract_explicit(
        self, utterance: str | None, session_id: str | None, source_run_id: str | None
    ) -> GateResult:
        if utterance is None or not utterance.strip():
            return self._reject("empty")
        if self.is_sensitive(utterance):
            return self._reject("privacy_blocked")
        for matcher in (self._match_temp, self._match_fan, self._match_media, self._match_name):
            entry = matcher(utterance)
            if entry is not None:
                return self._accept(entry, session_id, source_run_id, "explicit_preference")
        return self._reject("no_explicit_preference")

    def try_from_repeated(
        self,
        key: str,
        value: str,
        domain: str,
        consistent_count: int,
        session_id: str | None,
        source_run_id: str | None,
    ) -> GateResult:
        if consistent_count < 2:
            return self._reject("need_repeat_consistency")
        if source_run_id is None or not str(source_run_id).strip():
            return self._reject("missing_source")
        if self.is_sensitive(value):
            return self._reject("privacy_blocked")
        entry = MemoryEntry(
            category="preference",
            key=key,
            value=value,
            domain=domain,
            confidence=min(0.95, 0.6 + 0.1 * consistent_count),
            note="repeated_consistency",
        )
        return self._accept(entry, session_id, source_run_id, "repeated_consistency")

    def is_sensitive(self, text: str | None) -> bool:
        if text is None:
            return False
        lowered = text.lower()
        for token in _SENSITIVE:
            if token.lower() in lowered:
                return True
        return bool(re.search(r"\d{11}", text) or re.search(r"\d{15,18}", text))

    def allowed_keys(self) -> list[str]:
        return ["cabin_temperature", "cabin_fan", "media_volume", "address_name"]

    def _match_temp(self, text: str) -> MemoryEntry | None:
        match = _EXPLICIT_TEMP.search(text)
        if not match:
            return None
        value = int(match.group(1))
        if value < 16 or value > 30:
            return None
        return MemoryEntry(
            category="preference",
            key="cabin_temperature",
            value=str(value),
            domain="cabin",
            confidence=0.95,
        )

    def _match_fan(self, text: str) -> MemoryEntry | None:
        match = _EXPLICIT_FAN.search(text)
        if not match:
            return None
        value = int(match.group(1))
        if value < 0 or value > 7:
            return None
        return MemoryEntry(
            category="preference",
            key="cabin_fan",
            value=str(value),
            domain="cabin",
            confidence=0.9,
        )

    def _match_media(self, text: str) -> MemoryEntry | None:
        match = _EXPLICIT_MEDIA.search(text)
        if not match:
            return None
        value = int(match.group(1))
        if value < 0 or value > 40:
            return None
        return MemoryEntry(
            category="preference",
            key="media_volume",
            value=str(value),
            domain="media",
            confidence=0.85,
        )

    def _match_name(self, text: str) -> MemoryEntry | None:
        if not any(token in text for token in ("记住", "叫我", "称呼")):
            return None
        match = _EXPLICIT_NAME.search(text)
        if not match:
            return None
        name = match.group(1)
        if name in _NAME_BLOCKLIST:
            return None
        return MemoryEntry(
            category="preference",
            key="address_name",
            value=name,
            domain="general",
            confidence=0.8,
        )

    def _accept(
        self,
        entry: MemoryEntry,
        session_id: str | None,
        source_run_id: str | None,
        reason: str,
    ) -> GateResult:
        if source_run_id is None or not str(source_run_id).strip():
            return self._reject("missing_source")
        entry.session_id = session_id or "local"
        entry.source_run_id = source_run_id
        return GateResult(True, reason, entry)

    @staticmethod
    def _reject(reason: str) -> GateResult:
        return GateResult(False, reason, None)

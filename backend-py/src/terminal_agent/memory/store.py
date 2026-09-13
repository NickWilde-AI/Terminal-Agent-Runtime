"""SQLite-backed long-term memory with in-memory fallback for tests."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from terminal_agent.config import Settings, get_settings
from terminal_agent.contracts import new_id, now
from terminal_agent.memory.entry import MemoryEntry


class MemoryStore:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.db_path = Path(self.settings.sqlite_path)
        self._memory_fallback: list[MemoryEntry] = []
        self._use_sqlite = False
        self._initialized = False

    def init(self) -> None:
        self._use_sqlite = str(self.settings.persistence).lower() == "sqlite"
        self._initialized = True
        if not self._use_sqlite:
            return
        parent = self.db_path.parent
        parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as conn:
            conn.execute(
                """
                create table if not exists memories (
                  id text primary key,
                  session_id text not null,
                  category text not null,
                  key text not null,
                  value text not null,
                  domain text not null,
                  source_run_id text not null,
                  created_at text not null,
                  confidence real not null,
                  hit_count integer not null,
                  last_hit_at text,
                  active integer not null,
                  note text,
                  tenant_id text not null default 'local'
                )
                """
            )
            try:
                conn.execute("alter table memories add column tenant_id text not null default 'local'")
            except sqlite3.OperationalError:
                pass
            conn.commit()

    def save(self, entry: MemoryEntry) -> MemoryEntry:
        self._ensure_init()
        if not entry.id:
            entry.id = new_id("mem")
        if entry.created_at is None:
            entry.created_at = now()
        if not self._use_sqlite:
            for existing in self._memory_fallback:
                if (
                    existing.active
                    and existing.session_id == entry.session_id
                    and existing.tenant_id == (entry.tenant_id or "local")
                    and existing.key == entry.key
                ):
                    existing.active = False
            self._memory_fallback.append(entry)
            return entry
        try:
            with self._conn() as conn:
                conn.execute(
                    "update memories set active=0 where session_id=? and tenant_id=? and key=? and active=1",
                    (entry.session_id, entry.tenant_id or "local", entry.key),
                )
                conn.execute(
                    """
                    insert into memories(
                      id,session_id,category,key,value,domain,source_run_id,created_at,
                      confidence,hit_count,last_hit_at,active,note,tenant_id
                    ) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    self._bind(entry),
                )
                conn.commit()
        except Exception as exc:  # noqa: BLE001 — mirror Java IllegalStateException wrapping
            raise RuntimeError(f"memory save failed: {exc}") from exc
        return entry

    def list_active(self, session_id: str | None, tenant_id: str | None = None) -> list[MemoryEntry]:
        self._ensure_init()
        sid = session_id or "local"
        tenant = tenant_id or "local"
        if not self._use_sqlite:
            return sorted(
                [
                    m
                    for m in self._memory_fallback
                    if m.active and self._session_matches(m, sid) and (m.tenant_id or "local") == tenant
                ],
                key=lambda m: m.created_at or datetime.min,
                reverse=True,
            )
        try:
            with self._conn() as conn:
                rows = conn.execute(
                    "select * from memories where active=1 and session_id=? and tenant_id=? order by created_at desc",
                    (sid, tenant),
                ).fetchall()
            return [self._from_row(row) for row in rows]
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"memory list failed: {exc}") from exc

    def list_history(self, session_id: str | None, key: str) -> list[MemoryEntry]:
        self._ensure_init()
        sid = session_id or "local"
        if not self._use_sqlite:
            return sorted(
                [m for m in self._memory_fallback if self._session_matches(m, sid) and m.key == key],
                key=lambda m: m.created_at or datetime.min,
                reverse=True,
            )
        try:
            with self._conn() as conn:
                rows = conn.execute(
                    "select * from memories where session_id=? and key=? order by created_at desc",
                    (sid, key),
                ).fetchall()
            return [self._from_row(row) for row in rows]
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"memory history failed: {exc}") from exc

    def find_by_id(self, id_: str) -> MemoryEntry | None:
        self._ensure_init()
        if not self._use_sqlite:
            for entry in self._memory_fallback:
                if entry.id == id_:
                    return entry
            return None
        try:
            with self._conn() as conn:
                row = conn.execute("select * from memories where id=?", (id_,)).fetchone()
            return self._from_row(row) if row else None
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"memory find failed: {exc}") from exc

    def soft_delete(self, id_: str) -> bool:
        self._ensure_init()
        if not self._use_sqlite:
            found = self.find_by_id(id_)
            if found is None:
                return False
            found.active = False
            return True
        try:
            with self._conn() as conn:
                cursor = conn.execute("update memories set active=0 where id=?", (id_,))
                conn.commit()
                return cursor.rowcount > 0
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"memory delete failed: {exc}") from exc

    def mark_hit(self, id_: str) -> None:
        self._ensure_init()
        hit_at = now()
        if not self._use_sqlite:
            found = self.find_by_id(id_)
            if found is not None:
                found.hit_count += 1
                found.last_hit_at = hit_at
            return
        try:
            with self._conn() as conn:
                conn.execute(
                    "update memories set hit_count=hit_count+1, last_hit_at=? where id=?",
                    (hit_at.isoformat(), id_),
                )
                conn.commit()
        except Exception:  # noqa: BLE001 — Java swallows
            return

    def clear_session(self, session_id: str | None) -> None:
        self._ensure_init()
        sid = session_id or "local"
        if not self._use_sqlite:
            self._memory_fallback = [m for m in self._memory_fallback if not self._session_matches(m, sid)]
            return
        try:
            with self._conn() as conn:
                conn.execute("delete from memories where session_id=?", (sid,))
                conn.commit()
        except Exception:  # noqa: BLE001
            return

    def _ensure_init(self) -> None:
        if not self._initialized:
            self.init()

    @staticmethod
    def _session_matches(entry: MemoryEntry, session_id: str | None) -> bool:
        return (session_id or "local") == entry.session_id

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path.resolve()))
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _bind(entry: MemoryEntry) -> tuple[Any, ...]:
        return (
            entry.id,
            entry.session_id,
            entry.category,
            entry.key,
            entry.value,
            entry.domain,
            entry.source_run_id,
            entry.created_at.isoformat() if entry.created_at else now().isoformat(),
            entry.confidence,
            entry.hit_count,
            entry.last_hit_at.isoformat() if entry.last_hit_at else None,
            1 if entry.active else 0,
            entry.note,
            entry.tenant_id or "local",
        )

    @staticmethod
    def _from_row(row: sqlite3.Row) -> MemoryEntry:
        last_hit = row["last_hit_at"]
        return MemoryEntry(
            id=row["id"],
            session_id=row["session_id"],
            category=row["category"],
            key=row["key"],
            value=row["value"],
            domain=row["domain"],
            source_run_id=row["source_run_id"],
            created_at=datetime.fromisoformat(row["created_at"]),
            confidence=float(row["confidence"]),
            hit_count=int(row["hit_count"]),
            last_hit_at=datetime.fromisoformat(last_hit) if last_hit else None,
            active=int(row["active"]) == 1,
            note=row["note"],
            tenant_id=row["tenant_id"] if "tenant_id" in row.keys() else "local",
        )

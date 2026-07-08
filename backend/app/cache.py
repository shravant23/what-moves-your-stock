"""Read-through cache helpers over the SQLite CacheEntry table.

Every external fetch in Prism goes through these: pass a ttl to allow
refreshing (e.g. macro series daily), or ttl=None for immutable content
(a filed 10-K never changes, so it is never re-fetched)."""

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlmodel import select

from .db import CacheEntry, get_session, init_db

init_db()


def cache_get(key: str, ttl: timedelta | None = None) -> str | None:
    """Return the cached value, or None if absent or older than ttl.
    ttl=None means the entry never expires."""
    with get_session() as session:
        entry = session.exec(select(CacheEntry).where(CacheEntry.key == key)).first()
        if entry is None:
            return None
        if ttl is not None:
            fetched = entry.fetched_at
            if fetched.tzinfo is None:
                fetched = fetched.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) - fetched > ttl:
                return None
        return entry.value


def cache_set(key: str, value: str) -> None:
    with get_session() as session:
        entry = session.get(CacheEntry, key)
        now = datetime.now(timezone.utc)
        if entry is None:
            session.add(CacheEntry(key=key, value=value, fetched_at=now))
        else:
            entry.value = value
            entry.fetched_at = now
            session.add(entry)
        session.commit()


def cache_keys(prefix: str) -> list[str]:
    with get_session() as session:
        rows = session.exec(
            select(CacheEntry.key).where(CacheEntry.key.startswith(prefix))  # type: ignore[union-attr]
        ).all()
    return sorted(rows)


def cache_get_json(key: str, ttl: timedelta | None = None) -> Any | None:
    raw = cache_get(key, ttl)
    return None if raw is None else json.loads(raw)


def cache_set_json(key: str, value: Any) -> None:
    cache_set(key, json.dumps(value))

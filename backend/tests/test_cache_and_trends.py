"""SQLite cache TTL semantics + trend topic selection."""

from datetime import datetime, timedelta, timezone

from sqlmodel import select

from app.cache import cache_get, cache_get_json, cache_set, cache_set_json
from app.db import CacheEntry, get_session
from app.trends import select_trend_exposures

from .conftest import make_exposure, make_profile

# ----------------------------------------------------------------- cache


def test_cache_roundtrip():
    cache_set("t:key", "value")
    assert cache_get("t:key") == "value"
    assert cache_get("t:missing") is None


def test_cache_json_roundtrip():
    cache_set_json("t:json", {"a": [1, 2]})
    assert cache_get_json("t:json") == {"a": [1, 2]}


def test_cache_overwrite_updates_value():
    cache_set("t:ow", "one")
    cache_set("t:ow", "two")
    assert cache_get("t:ow") == "two"


def test_ttl_expiry():
    cache_set("t:ttl", "fresh")
    assert cache_get("t:ttl", ttl=timedelta(hours=1)) == "fresh"
    # age the entry artificially
    with get_session() as session:
        entry = session.exec(select(CacheEntry).where(CacheEntry.key == "t:ttl")).one()
        entry.fetched_at = datetime.now(timezone.utc) - timedelta(hours=2)
        session.add(entry)
        session.commit()
    assert cache_get("t:ttl", ttl=timedelta(hours=1)) is None
    assert cache_get("t:ttl", ttl=None) == "fresh"  # ttl=None never expires


# ------------------------------------------------------- trend selection


def test_trend_selection_dedupes_by_category_and_orders_by_magnitude():
    exposures = [
        make_exposure(name="Minor Thing", category="currency", magnitude="minor"),
        make_exposure(name="Copper", category="commodity_output", magnitude="critical"),
        make_exposure(name="Gold", category="commodity_output", magnitude="significant"),
        make_exposure(name="Indonesia", category="geography", magnitude="critical"),
    ]
    picked = select_trend_exposures(make_profile(exposures))
    names = [e.name for e in picked]
    assert names[0] in ("Copper", "Indonesia")  # criticals first
    assert "Gold" not in names  # same category as Copper -> deduped
    assert "Minor Thing" in names  # unique category still included


def test_trend_selection_caps_at_six():
    categories = [
        "commodity_input", "commodity_output", "geography", "customer_concentration",
        "supplier_concentration", "interest_rates", "currency", "regulation", "demand_driver",
    ]
    exposures = [
        make_exposure(name=f"E{i}", category=c, magnitude="moderate")
        for i, c in enumerate(categories)
    ]
    assert len(select_trend_exposures(make_profile(exposures))) == 6

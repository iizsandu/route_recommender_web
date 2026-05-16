# backend/tests/test_routing.py

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import app.services.routing as routing_module
from app.services.routing import _sample_waypoints, _cache_key
from app.utils.cache import TTLCache

# ---------------------------------------------------------------------------
# Pure-function tests — no I/O, no mocking needed
# ---------------------------------------------------------------------------

def test_sample_waypoints_empty():
    """Empty coordinate list returns empty waypoints list."""
    assert _sample_waypoints([]) == []


def test_sample_waypoints_single_coordinate():
    """A single coordinate emits exactly one waypoint."""
    result = _sample_waypoints([[77.2, 28.6]])
    assert result == [(28.6, 77.2)]


def test_sample_waypoints_flips_lng_lat():
    """GeoJSON [lng, lat] is flipped to (lat, lng) in the output."""
    # Two points: start only (they are the same point so distance=0).
    result = _sample_waypoints([[77.2090, 28.6139]])
    assert result[0] == (28.6139, 77.2090)


def test_sample_waypoints_interval():
    """A route longer than WAYPOINT_INTERVAL_M emits waypoints at ~100m intervals."""
    # Two points roughly 500m apart along a straight line in Delhi.
    # Expected: start + at least one intermediate sample before the end.
    coords = [
        [77.2000, 28.6000],
        [77.2060, 28.6000],  # ~530m east at this latitude
    ]
    result = _sample_waypoints(coords)
    assert len(result) >= 2
    # All outputs must be (lat, lng) — lat first.
    for lat, lng in result:
        assert 28.0 <= lat <= 30.0
        assert 76.0 <= lng <= 79.0


def test_cache_key_rounds_to_4dp():
    """_cache_key rounds coordinates to 4 decimal places.

    Values chosen so both inputs share the same 4dp rounded value:
    e.g. 28.61391 and 28.61393 both round to 28.6139 (5th digit < 5).
    """
    key1 = _cache_key((28.61391, 77.20901), (28.70001, 77.30001), "driving-car")
    key2 = _cache_key((28.61393, 77.20903), (28.70003, 77.30003), "driving-car")
    assert key1 == key2


# ---------------------------------------------------------------------------
# TTLCache unit tests
# ---------------------------------------------------------------------------

def test_ttl_cache_miss_returns_none():
    cache = TTLCache(ttl_seconds=60)
    assert cache.get("missing") is None


def test_ttl_cache_hit_returns_value():
    cache = TTLCache(ttl_seconds=60)
    cache.set("k", {"routes": []})
    assert cache.get("k") == {"routes": []}


def test_ttl_cache_expiry(monkeypatch):
    """After TTL elapses, get() returns None and clears the entry."""
    import time as _time
    cache = TTLCache(ttl_seconds=10)

    now = _time.monotonic()
    monkeypatch.setattr("app.utils.cache.time.monotonic", lambda: now)
    cache.set("k", "value")

    # Advance clock past TTL.
    monkeypatch.setattr("app.utils.cache.time.monotonic", lambda: now + 11)
    assert cache.get("k") is None
    assert "k" not in cache._store


# ---------------------------------------------------------------------------
# get_routes integration tests (httpx mocked)
# ---------------------------------------------------------------------------

_ORS_RESPONSE = {
    "features": [
        {
            "geometry": {
                "type": "LineString",
                "coordinates": [[77.2, 28.6], [77.21, 28.61]],
            },
            "properties": {
                "summary": {"duration": 300.0, "distance": 1500.0},
            },
        }
    ]
}


@pytest.mark.asyncio
async def test_get_routes_parses_ors_response():
    """get_routes returns a list of dicts with the expected keys and values."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = _ORS_RESPONSE
    mock_resp.raise_for_status.return_value = None

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_resp)

    routing_module._cache.clear()
    with patch("app.services.routing.httpx.AsyncClient", return_value=mock_client):
        routes = await routing_module.get_routes((28.6, 77.2), (28.61, 77.21))

    assert len(routes) == 1
    assert set(routes[0].keys()) == {"geometry", "duration_sec", "distance_m", "waypoints"}
    assert routes[0]["duration_sec"] == 300.0
    assert routes[0]["distance_m"] == 1500.0
    assert isinstance(routes[0]["waypoints"], list)


@pytest.mark.asyncio
async def test_get_routes_cache_hit():
    """get_routes returns cached result without calling httpx when the cache is warm."""
    routing_module._cache.clear()

    fake_routes = [
        {"geometry": {}, "duration_sec": 100.0, "distance_m": 500.0, "waypoints": []}
    ]
    key = _cache_key((28.6, 77.2), (28.7, 77.3), "driving-car")
    routing_module._cache.set(key, fake_routes)

    with patch("app.services.routing.httpx.AsyncClient") as mock_cls:
        result = await routing_module.get_routes((28.6, 77.2), (28.7, 77.3))

    assert result == fake_routes
    mock_cls.assert_not_called()

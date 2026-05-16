# backend/app/services/geocoding.py

from __future__ import annotations

import logging

import httpx

from app.config import Settings
from app.utils.cache import TTLCache

logger = logging.getLogger(__name__)
settings = Settings()

# 24h cache — addresses don't move.
_cache: TTLCache = TTLCache(ttl_seconds=24 * 3600)

# Delhi-NCR bounding box used to restrict geocoding results.
_BBOX = {
    "boundary.rect.min_lat": 28.0,
    "boundary.rect.max_lat": 29.5,
    "boundary.rect.min_lon": 76.5,
    "boundary.rect.max_lon": 78.0,
}


async def geocode(address: str) -> tuple[float, float]:
    """Return (lat, lng) for address. Raises ValueError if not found."""
    key = address.strip().lower()
    cached = _cache.get(key)
    if cached is not None:
        return cached

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            f"{settings.ORS_BASE_URL}/geocode/search",
            params={
                "api_key": settings.ORS_API_KEY,
                "text": address,
                "size": 1,
                **_BBOX,
            },
        )
        resp.raise_for_status()

    features = resp.json().get("features", [])
    if not features:
        raise ValueError(f"could not geocode address: {address!r}")

    # WHY [1], [0]: GeoJSON coordinates are [lng, lat] — note the reversal.
    coords = features[0]["geometry"]["coordinates"]
    result: tuple[float, float] = (coords[1], coords[0])

    _cache.set(key, result)
    logger.info("geocoded %r → (%.4f, %.4f)", address, *result)
    return result

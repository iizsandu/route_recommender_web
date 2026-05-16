# backend/app/schemas/routes.py

from datetime import datetime, timezone
from typing import Literal, Union

from pydantic import BaseModel, Field


class LatLng(BaseModel):
    lat: float
    lng: float


class RouteRequest(BaseModel):
    # WHY Union not X|Y: Python 3.9 doesn't support the X|Y union syntax in
    # runtime type annotations. Union[X, Y] works on 3.9+.
    # (from __future__ import annotations defers evaluation but Pydantic 2
    # still evaluates them at model construction time via get_type_hints.)
    origin:      Union[LatLng, str]
    destination: Union[LatLng, str]
    depart_time: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )


class RouteOption(BaseModel):
    geometry:     dict        # GeoJSON LineString
    duration_sec: float
    distance_m:   float
    # WHY Literal: enforces the 3-band contract at the type level. The raw
    # float score is never returned to the client — only the band label.
    risk_band:    Literal["Low", "Medium", "High"]


class RouteResponse(BaseModel):
    routes: list[RouteOption]

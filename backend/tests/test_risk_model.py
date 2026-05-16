# backend/tests/test_risk_model.py

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from app.services.risk_model import RouteRiskResult, score_points_batch, score_route


def test_score_points_batch_happy_path(fake_model_dict):
    """score_points_batch returns a non-negative score array of the correct shape."""
    with patch("app.services.risk_model._MODEL", fake_model_dict), \
         patch("app.services.risk_model._LGB_MODELS", None):
        scores = score_points_batch(
            lats=np.array([28.6, 28.7]),
            lngs=np.array([77.2, 77.3]),
            hour=12,  # daytime band → multiplier 0.7
        )

    assert scores.shape == (2,)
    assert (scores >= 0).all()
    # fake_kde returns 1.0 per point; weight=3.0; time_mod=0.7 → expected 2.1
    assert scores == pytest.approx(np.array([2.1, 2.1]))


def test_score_route_zero_waypoints(fake_model_dict):
    """score_route with an empty waypoints list returns a zeroed RouteRiskResult."""
    with patch("app.services.risk_model._MODEL", fake_model_dict), \
         patch("app.services.risk_model._LGB_MODELS", None):
        result = score_route(
            waypoints=[],
            depart_time=datetime(2026, 5, 16, 12, 0, tzinfo=timezone.utc),
            route_eta_sec=0.0,
        )

    assert isinstance(result, RouteRiskResult)
    assert result.total_score == 0.0
    assert result.per_waypoint_scores == []
    assert result.n_waypoints == 0


def test_score_route_unknown_category_skipped():
    """A category with weight=0.0 contributes zero score and its KDE is not called."""
    fraud_kde = MagicMock()
    zero_weight_model = {
        "models":       {"Fraud": fraud_kde},
        "weights":      {"Fraud": 0.0},
        "fit_at":       "2026-05-16T00:00:00",
        "n_categories": 1,
    }

    with patch("app.services.risk_model._MODEL", zero_weight_model), \
         patch("app.services.risk_model._LGB_MODELS", None):
        result = score_route(
            waypoints=[(28.6, 77.2), (28.7, 77.3)],
            depart_time=datetime(2026, 5, 16, 12, 0, tzinfo=timezone.utc),
            route_eta_sec=600.0,
        )

    assert result.total_score == pytest.approx(0.0)
    # Weight=0.0 short-circuits the KDE call — the mock must never be invoked.
    fraud_kde.assert_not_called()

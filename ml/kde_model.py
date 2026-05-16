# ml/kde_model.py
"""
Shared KDE model class used by both train_kde.py (training) and
risk_model.py (inference).

WHY a separate module: FixedBandwidthKDE must be importable from a stable,
consistent module path so pickle can serialise and deserialise it correctly.
If it were defined inside train_kde.py (run as __main__), pickle would record
the class path as '__main__.FixedBandwidthKDE'. Any other process loading the
.pkl would fail with:
    AttributeError: Can't get attribute 'FixedBandwidthKDE' on <module '__main__'>

Defining it here means pickle records 'ml.kde_model.FixedBandwidthKDE' —
a stable, importable path that works in any context.
"""

from __future__ import annotations

import numpy as np
from scipy.stats import gaussian_kde


class FixedBandwidthKDE(gaussian_kde):
    """scipy.stats.gaussian_kde with a fixed, picklable bandwidth.

    Standard gaussian_kde accepts bw_method as a scalar float, but stores it
    internally via set_bandwidth() which creates a lambda. Lambdas are not
    picklable, causing:
        AttributeError: Can't get local object
            'gaussian_kde.set_bandwidth.<locals>.<lambda>'

    This subclass overrides covariance_factor() as a regular method, returning
    the fixed bandwidth directly. No lambda — fully picklable.

    The bandwidth value is in the same units as the data (decimal degrees here).
    0.015° ≈ 1.5 km at Delhi's latitude — validated in EDA Part 4.

    Usage:
        kde = FixedBandwidthKDE(coords, bandwidth=0.015, weights=w)
        scores = kde(query_points)   # shape (n_query,)
    """

    def __init__(
        self,
        dataset: np.ndarray,
        bandwidth: float,
        weights: np.ndarray | None = None,
    ) -> None:
        self._fixed_bandwidth = bandwidth
        # bw_method='silverman' is a throwaway — covariance_factor() override
        # below replaces it immediately after super().__init__ completes.
        super().__init__(dataset, bw_method="silverman", weights=weights)

    def covariance_factor(self) -> float:  # type: ignore[override]
        return self._fixed_bandwidth

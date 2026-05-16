# ml/generate_heatmap.py
"""
Pre-compute a static risk heatmap as GeoJSON over a 0.02° grid.

Scored at hour=12 (daytime — neutral baseline). The heatmap is regenerated
weekly alongside the retrain cron so it reflects the current KDE model.

Output: ml/artifacts/heatmap.geojson

Usage:
    python -m ml.generate_heatmap
    python -m ml.generate_heatmap --artifacts ml/artifacts
"""

from __future__ import annotations

import argparse
import json
import logging
import pickle
import sys
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

# Delhi-NCR bounds (matches ingest.py)
LAT_MIN, LAT_MAX = 28.0, 29.5
LNG_MIN, LNG_MAX = 76.5, 78.0
GRID_STEP = 0.02        # WHY 0.02°: ~2.2 km spacing; ~5,700 grid points total —
                        # fine enough to show neighbourhood-level risk, small enough
                        # to serve as a static JSON file (~400 KB).
HOUR = 12               # WHY midday: time-neutral baseline; time modifier = 0.7 (daytime)
ARTIFACTS_DIR = Path(__file__).parent / "artifacts"

# Banding thresholds (matches backend/app/config.py defaults)
BAND_LOW  = 0.0713
BAND_HIGH = 0.9142

# Time-of-day multipliers (mirrors risk_model.py _TIME_BANDS)
_TIME_BANDS = (
    (22, 24, 2.5), (0, 5, 2.5),
    (18, 22, 1.5),
    (5,  9,  1.0),
    (9,  18, 0.7),
)


def _time_modifier(hour: int) -> float:
    for start, end, mult in _TIME_BANDS:
        if start <= hour < end:
            return mult
    return 1.0


def _load_models(artifacts_dir: Path) -> tuple[dict, dict]:
    """Load kde_*.pkl files and return (models, weights) dicts."""
    pkl_files = sorted(artifacts_dir.glob("kde_*.pkl"))
    if not pkl_files:
        raise FileNotFoundError(f"No kde_*.pkl in {artifacts_dir} — run train_kde.py first.")

    # WHY insert repo root: FixedBandwidthKDE lives in ml.kde_model which is
    # not importable unless the repo root is on sys.path.
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    models: dict = {}
    weights: dict = {}
    for pkl_path in pkl_files:
        with open(pkl_path, "rb") as f:
            artifact = pickle.load(f)
        cat = artifact["category"]
        models[cat]  = artifact["kde"]
        weights[cat] = artifact["weight"]

    logger.info("loaded %d KDE models from %s", len(models), artifacts_dir)
    return models, weights


def _score_grid(models: dict, weights: dict) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Score every (lat, lng) grid point. Returns (lats, lngs, scores) arrays."""
    lats = np.arange(LAT_MIN, LAT_MAX + GRID_STEP, GRID_STEP)
    lngs = np.arange(LNG_MIN, LNG_MAX + GRID_STEP, GRID_STEP)

    # Build mesh and flatten for vectorised KDE evaluation
    lat_grid, lng_grid = np.meshgrid(lats, lngs, indexing="ij")
    flat_lats = lat_grid.ravel()
    flat_lngs = lng_grid.ravel()
    points = np.vstack([flat_lats, flat_lngs])   # shape (2, n)

    scores = np.zeros(points.shape[1])
    for cat, kde in models.items():
        w = weights.get(cat, 0.0)
        if w == 0.0:
            continue
        scores += kde(points) * w

    scores *= _time_modifier(HOUR)
    logger.info(
        "scored %d grid points  min=%.4f  max=%.4f  mean=%.4f",
        len(scores), scores.min(), scores.max(), scores.mean(),
    )
    return flat_lats, flat_lngs, scores


def _score_dense_grid(
    models: dict, weights: dict, grid_size: int = 300
) -> np.ndarray:
    """Score KDE on a fine (grid_size × grid_size) grid for PNG rendering."""
    lats = np.linspace(LAT_MIN, LAT_MAX, grid_size)
    lngs = np.linspace(LNG_MIN, LNG_MAX, grid_size)
    lat_g, lng_g = np.meshgrid(lats, lngs, indexing="ij")
    pts = np.vstack([lat_g.ravel(), lng_g.ravel()])
    scores = np.zeros(pts.shape[1])
    for cat, kde in models.items():
        w = weights.get(cat, 0.0)
        if w > 0:
            scores += kde(pts) * w
    scores *= _time_modifier(HOUR)
    logger.info(
        "dense grid %dx%d  min=%.4f  max=%.4f",
        grid_size, grid_size, scores.min(), scores.max(),
    )
    return scores.reshape(grid_size, grid_size)


def _scores_to_image(scores_2d: np.ndarray, out_path: Path) -> None:
    """Render the 2-D score array as a transparent RGBA PNG heatmap."""
    import matplotlib.colors as mcolors
    import matplotlib.pyplot as plt

    # Log-percentile normalise to [0, 1]
    p1  = float(np.percentile(scores_2d, 1))
    p99 = float(np.percentile(scores_2d, 99))
    clipped = np.clip(scores_2d, p1, p99)
    log_s = np.log1p(clipped)
    lo, hi = float(log_s.min()), float(log_s.max())
    norm = (log_s - lo) / (hi - lo + 1e-10)

    # RGBA colormap: transparent in safe zones, yellow → orange → crimson
    cmap = mcolors.LinearSegmentedColormap.from_list(
        "crime_risk",
        [
            (0.00, (1.0, 1.0, 1.0, 0.00)),
            (0.12, (1.0, 0.95, 0.5, 0.18)),
            (0.30, (1.0, 0.70, 0.1, 0.55)),
            (0.55, (1.0, 0.25, 0.0, 0.78)),
            (0.75, (0.85, 0.00, 0.0, 0.88)),
            (1.00, (0.45, 0.00, 0.0, 0.95)),
        ],
        N=512,
    )

    # flipud: numpy rows go top→bottom but latitude increases bottom→top
    rgba = cmap(np.flipud(norm))
    plt.imsave(out_path, rgba)
    logger.info("heatmap image written: %s  (%.0f KB)", out_path, out_path.stat().st_size / 1024)


def _band(score: float) -> str:
    if score < BAND_LOW:
        return "Low"
    if score < BAND_HIGH:
        return "Medium"
    return "High"


def _normalise_scores(scores: np.ndarray) -> np.ndarray:
    """Map raw KDE scores to [0, 1] using log-percentile normalisation.

    WHY log: raw KDE scores are heavily right-skewed (a few peak zones are
    10-50× higher than the median). Linear normalisation would compress most
    of the map to near-zero, making the heatmap look like a few bright spots.
    Log normalisation preserves relative differences while making variation
    visible across the full range.

    WHY percentile clip: removes the effect of extreme outliers (e.g. a
    single grid cell that is 5× the 99th percentile would dominate min-max
    normalisation). Clip to [p1, p99] before rescaling.
    """
    p1, p99 = float(np.percentile(scores, 1)), float(np.percentile(scores, 99))
    clipped = np.clip(scores, p1, p99)
    log_s   = np.log1p(clipped)               # log(1+x): safe for x=0
    lo, hi  = log_s.min(), log_s.max()
    if hi == lo:                               # degenerate: all identical scores
        return np.zeros_like(scores)
    return (log_s - lo) / (hi - lo)


def _to_geojson(lats: np.ndarray, lngs: np.ndarray, scores: np.ndarray) -> dict:
    """Build a GeoJSON FeatureCollection of Point features."""
    norm = _normalise_scores(scores)
    features = []
    for lat, lng, score, s_norm in zip(lats, lngs, scores, norm):
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                # WHY [lng, lat]: GeoJSON spec is [longitude, latitude]
                "coordinates": [round(float(lng), 4), round(float(lat), 4)],
            },
            "properties": {
                "risk_band":  _band(float(score)),
                # WHY score_norm not raw score: heatmap-weight needs a float
                # for smooth rendering; using normalized [0,1] avoids exposing
                # the raw KDE density (consistent with backend policy).
                "score_norm": round(float(s_norm), 4),
            },
        })
    return {"type": "FeatureCollection", "features": features}


def generate(artifacts_dir: Path) -> Path:
    out_path       = artifacts_dir / "heatmap.geojson"
    out_image_path = artifacts_dir / "heatmap.png"

    models, weights = _load_models(artifacts_dir)

    lats, lngs, scores = _score_grid(models, weights)
    geojson = _to_geojson(lats, lngs, scores)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(geojson, f, separators=(",", ":"))
    size_kb = out_path.stat().st_size / 1024
    logger.info("heatmap written: %s  (%.0f KB, %d features)", out_path, size_kb, len(geojson["features"]))

    scores_2d = _score_dense_grid(models, weights, grid_size=300)
    _scores_to_image(scores_2d, out_image_path)

    return out_path


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="Generate static risk heatmap GeoJSON")
    parser.add_argument(
        "--artifacts", type=Path, default=ARTIFACTS_DIR,
        help="Directory containing kde_*.pkl files (default: ml/artifacts)",
    )
    args = parser.parse_args()
    generate(args.artifacts)

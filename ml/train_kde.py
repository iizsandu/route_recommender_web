# ml/train_kde.py

from __future__ import annotations

import logging
import pickle
from datetime import date, datetime, timezone
from pathlib import Path

import mlflow
import numpy as np
import pandas as pd
from scipy.stats import gaussian_kde

logger = logging.getLogger(__name__)

# Macro types that get their own KDE. Fraud weight=0.0 so excluded.
# Unknown is noise from failed LLM extraction — excluded.
TRAIN_MACROS: tuple[str, ...] = (
    "Sexual Violence", "Kidnapping", "Robbery", "Assault",
    "Murder", "Theft", "Drug", "Terrorism",
)

# Female-focused weights applied at route-scoring time (not here).
# Stored in the pkl so the backend doesn't need to re-declare them.
FEMALE_WEIGHTS: dict[str, float] = {
    "Sexual Violence": 3.0,
    "Kidnapping":      2.5,
    "Robbery":         2.0,
    "Assault":         1.5,
    "Murder":          1.5,
    "Theft":           0.7,
    "Drug":            0.5,
    "Terrorism":       1.0,
}

# WHY 10: gaussian_kde needs variance to compute bandwidth. Fewer than
# ~10 points produces an unreliable density estimate.
MIN_POINTS = 10

ARTIFACTS_DIR = Path(__file__).parent / "artifacts"

RECENCY_HALF_LIFE_DAYS = 90


def _recency_weights(df: pd.DataFrame) -> np.ndarray:
    # WHY utc today: effective_date may have been stored without timezone.
    # Using a consistent UTC reference prevents day-boundary drift.
    today = datetime.now(timezone.utc).date()

    dates = pd.to_datetime(df["effective_date"], errors="coerce").dt.date

    # WHY fillna with today: a record with no date gets age=0 → weight=1.0.
    # This is conservative — unknown-date crimes are treated as recent
    # rather than being silently down-weighted or dropped.
    dates = dates.fillna(today)

    age_days = np.array([(today - d).days for d in dates], dtype=float)

    # Exponential decay: w = exp(-age / half_life)
    weights = np.exp(-age_days / RECENCY_HALF_LIFE_DAYS)

    # WHY normalise: scipy's gaussian_kde requires weights that sum to 1.
    # Without this, the density integral won't equal 1.0.
    return weights / weights.sum()


def _fit_one(latlng: np.ndarray, weights: np.ndarray) -> gaussian_kde:
    # WHY shape (2, n): scipy's gaussian_kde expects (dimensions, samples).
    # Our latlng arrives as (n, 2) from DataFrame — transpose before passing.
    return gaussian_kde(
        latlng.T,
        # WHY lambda: gives access to kde.silverman_factor() at fit time
        # so we can halve it without computing it ourselves.
        bw_method=lambda k: k.silverman_factor() * 0.5,
        weights=weights,
    )


def _fit_all(df: pd.DataFrame) -> dict[str, gaussian_kde]:
    models: dict[str, gaussian_kde] = {}

    for macro in TRAIN_MACROS:
        subset = df[df["crime_macro"] == macro].copy()

        if len(subset) < MIN_POINTS:
            logger.warning(
                "skipping %s — only %d records (need %d)",
                macro, len(subset), MIN_POINTS,
            )
            continue

        weights = _recency_weights(subset)

        # WHY [["lat", "lng"]].values: produces shape (n, 2) numpy array.
        # _fit_one transposes to (2, n) internally.
        latlng = subset[["lat", "lng"]].values
        models[macro] = _fit_one(latlng, weights)

        logger.info("fitted KDE for %s  (n=%d)", macro, len(subset))

    return models


def run(snapshot_path: Path, artifacts_dir: Path = ARTIFACTS_DIR) -> Path:
    df = pd.read_parquet(snapshot_path)
    logger.info("loaded %d records from %s", len(df), snapshot_path)

    with mlflow.start_run():
        mlflow.log_params({
            "bw_silverman_factor": 0.5,
            "recency_half_life_days": RECENCY_HALF_LIFE_DAYS,
            "min_points_per_type": MIN_POINTS,
            "snapshot": snapshot_path.name,
        })

        models = _fit_all(df)

        if not models:
            raise ValueError("no macro types had enough records to fit — aborting")

        # Log per-type record counts as MLflow metrics
        for macro in TRAIN_MACROS:
            n = int((df["crime_macro"] == macro).sum())
            # WHY replace spaces: MLflow metric keys cannot contain spaces
            mlflow.log_metric(f"n_{macro.lower().replace(' ', '_')}", n)

        # Compute holdout log-likelihood per type (random 20% holdout)
        for macro, kde in models.items():
            subset = df[df["crime_macro"] == macro]
            holdout = subset.sample(frac=0.2, random_state=42)
            if len(holdout) < 2:
                continue
            latlng_holdout = holdout[["lat", "lng"]].values.T
            ll = float(kde.logpdf(latlng_holdout).sum())
            mlflow.log_metric(f"loglik_{macro.lower().replace(' ', '_')}", ll)

        # Build and save the pkl
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        out_path = artifacts_dir / f"kde_model_{date.today().isoformat()}.pkl"

        payload = {
            "models":      models,
            "weights":     FEMALE_WEIGHTS,
            "fit_at":      datetime.now(timezone.utc).isoformat(),
            "n_records":   len(df),
            "data_window": (
                str(df["effective_date"].min()),
                str(df["effective_date"].max()),
            ),
        }

        with open(out_path, "wb") as f:
            pickle.dump(payload, f)

        # WHY log_artifact after writing: MLflow copies the file into the
        # run's artifact store — the local pkl remains as a fast-access cache.
        mlflow.log_artifact(str(out_path))
        logger.info("model saved: %s", out_path)

    return out_path


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)

    if len(sys.argv) < 2:
        print("usage: python -m ml.train_kde <path/to/snapshot.parquet>")
        sys.exit(1)

    run(Path(sys.argv[1]))

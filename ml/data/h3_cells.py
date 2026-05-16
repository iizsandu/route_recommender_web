# ml/data/h3_cells.py
"""
Assign each crime record to an H3 res-7 cell and aggregate into
(cell × week) feature rows for LightGBM training.

Input:  ml/data/snapshots/crimes_YYYY-MM-DD.parquet   (from ingest.py)
Output: ml/data/snapshots/cell_features_YYYY-MM-DD.parquet

The output is a panel DataFrame: one row per (h3_cell, week_start).
Rows where no crime occurred that week have label=0; rows with ≥1 crime
have label=1. The Cartesian product ensures LightGBM sees the zero cases —
naively building rows only from crimes would give 100% prevalence and no
signal.

Usage:
    python -m ml.data.h3_cells --latest
    python -m ml.data.h3_cells --snapshot ml/data/snapshots/crimes_2026-05-15.parquet
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import h3
import numpy as np
import pandas as pd

from ml.data.category_mapping import KDE_ELIGIBLE

logger = logging.getLogger(__name__)

RESOLUTION = 7          # WHY 7: ~5.16 km² cells; ~350-400 cells over Delhi-NCR.
                        # Res 8 (~0.74 km²) gives ~2,800 cells — too sparse at 8k records.
SNAPSHOT_DIR = Path(__file__).parent / "snapshots"


# ── Filtering helpers ─────────────────────────────────────────────────────────

def _filter_crimes(df: pd.DataFrame) -> pd.DataFrame:
    """Apply the same 4-filter logic as train_kde.py to the crime snapshot."""
    mask = (
        df["lat"].notna() &
        df["lng"].notna() &
        df["is_delhi_crime"].fillna(False) &
        ~df["is_historical"].fillna(False) &
        df["crime_macro"].isin(KDE_ELIGIBLE)
    )
    filtered = df[mask].copy()
    logger.info("filtered %d / %d crimes for H3 cell assignment", len(filtered), len(df))
    return filtered


# ── H3 cell assignment ────────────────────────────────────────────────────────

def _assign_cells(df: pd.DataFrame) -> pd.DataFrame:
    """Add h3_cell and week_start columns to the crime DataFrame."""
    # WHY vectorised list comprehension not .apply(): h3.geo_to_h3 is a C
    # extension — a Python loop is faster than pandas apply() overhead here.
    df["h3_cell"] = [
        h3.geo_to_h3(lat, lng, RESOLUTION)
        for lat, lng in zip(df["lat"], df["lng"])
    ]

    # WHY W-MON period: normalises any date to the Monday that starts its
    # ISO week. Using period avoids tz-naive vs tz-aware datetime conflicts.
    df["week_start"] = (
        df["effective_date"]
        .dt.to_period("W-MON")
        .dt.start_time
        .dt.normalize()
    )
    return df


# ── Panel construction ────────────────────────────────────────────────────────

def _build_panel(crime_df: pd.DataFrame) -> pd.DataFrame:
    """Build the full (cell × week) Cartesian product.

    WHY Cartesian product: cells with zero crimes in a given week must appear
    as label=0 rows. If we only create rows from crime events, every row has
    label=1 — LightGBM would learn nothing (100% prevalence = no signal).
    """
    all_cells = sorted(crime_df["h3_cell"].unique())
    # WHY unique() not date_range: dt.to_period("W-MON").dt.start_time produces
    # Tuesday-aligned timestamps, but date_range(freq="W-MON") produces Mondays.
    # The merge in _add_crime_counts would find zero matches, giving 0% label
    # prevalence. Using the actual timestamps guarantees alignment.
    all_weeks = sorted(crime_df["week_start"].dropna().unique())

    logger.info(
        "building panel: %d cells × %d weeks = %d rows",
        len(all_cells), len(all_weeks), len(all_cells) * len(all_weeks),
    )

    index = pd.MultiIndex.from_product(
        [all_cells, all_weeks], names=["h3_cell", "week_start"]
    )
    panel = index.to_frame(index=False)
    panel["week_start"] = pd.to_datetime(panel["week_start"])
    return panel


# ── Weekly crime counts per macro type ───────────────────────────────────────

def _add_crime_counts(panel: pd.DataFrame, crime_df: pd.DataFrame) -> pd.DataFrame:
    """Pivot crime counts by macro type onto the panel.

    Each KDE_ELIGIBLE macro type becomes a column: crime_count_{slug}.
    Rows with no crime in that cell-week get 0.
    """
    # Build slug-safe column names
    slug = {macro: "crime_count_" + macro.lower().replace(" / ", "_").replace(" ", "_")
            for macro in KDE_ELIGIBLE}

    counts = (
        crime_df
        .groupby(["h3_cell", "week_start", "crime_macro"])
        .size()
        .reset_index(name="count")
        .pivot_table(
            index=["h3_cell", "week_start"],
            columns="crime_macro",
            values="count",
            fill_value=0,
        )
        .reset_index()
    )
    # Rename macro columns to crime_count_* slugs
    counts.rename(columns=slug, inplace=True)

    panel = panel.merge(counts, on=["h3_cell", "week_start"], how="left")
    # Fill cells/weeks with no crimes
    count_cols = list(slug.values())
    panel[count_cols] = panel[count_cols].fillna(0).astype(int)
    return panel, count_cols


# ── Rolling density features ──────────────────────────────────────────────────

def _add_rolling_features(panel: pd.DataFrame, count_cols: list[str]) -> pd.DataFrame:
    """Add 30-day and 90-day crime density lookback per cell.

    WHY shift(1) before rolling: density must be computed from crimes BEFORE
    the current week. Using current-week crimes as a feature would leak the
    label into the features (if label=1, current week has ≥1 crime → density>0).
    """
    panel = panel.sort_values(["h3_cell", "week_start"]).copy()
    panel["total_crimes"] = panel[count_cols].sum(axis=1)

    def rolling_lookback(group: pd.DataFrame) -> pd.DataFrame:
        past = group["total_crimes"].shift(1)           # exclude current week
        group["cell_density_30d"] = past.rolling(4, min_periods=1).sum()   # 4 weeks ≈ 30d
        group["cell_density_90d"] = past.rolling(13, min_periods=1).sum()  # 13 weeks ≈ 90d
        return group

    panel = (
        panel
        .groupby("h3_cell", group_keys=False)
        .apply(rolling_lookback)
    )
    panel[["cell_density_30d", "cell_density_90d"]] = (
        panel[["cell_density_30d", "cell_density_90d"]].fillna(0)
    )
    return panel


def _add_neighbour_density(panel: pd.DataFrame) -> pd.DataFrame:
    """Add mean 30-day density of the 6 immediate H3 neighbours.

    WHY neighbours: crime risk spills across cell boundaries. A cell with
    no crimes but surrounded by high-crime cells is riskier than an isolated
    zero-crime cell. This feature captures that spatial autocorrelation.

    WHY only 30d: 90d neighbour density is correlated with 30d and adds
    collinearity without much extra signal.
    """
    # Index for fast neighbour lookup: (cell, week_start) → density_30d
    lookup = panel.set_index(["h3_cell", "week_start"])["cell_density_30d"]

    def get_neighbour_density(row: pd.Series) -> float:
        # k_ring(cell, 1) returns the cell itself + its 6 neighbours
        neighbours = h3.k_ring(row["h3_cell"], 1) - {row["h3_cell"]}
        densities = []
        for n in neighbours:
            try:
                densities.append(lookup.loc[(n, row["week_start"])])
            except KeyError:
                # Neighbour cell has no crimes at all → treat as 0 density
                densities.append(0.0)
        return float(np.mean(densities)) if densities else 0.0

    logger.info("computing neighbour densities (may take ~30s for large panels)...")
    panel["neighbour_density_30d"] = panel.apply(get_neighbour_density, axis=1)
    return panel


# ── Temporal features ─────────────────────────────────────────────────────────

def _add_temporal_features(panel: pd.DataFrame) -> pd.DataFrame:
    """Add calendar features that capture seasonality."""
    panel["month"] = panel["week_start"].dt.month
    panel["week_of_year"] = panel["week_start"].dt.isocalendar().week.astype(int)
    # WHY day_of_week=0: weekly rows always start Monday. Included for schema
    # compatibility with the spec; LightGBM will assign it zero importance.
    panel["day_of_week"] = 0
    panel["is_weekend"] = 0
    return panel


# ── Label ─────────────────────────────────────────────────────────────────────

def _add_label(panel: pd.DataFrame, count_cols: list[str]) -> pd.DataFrame:
    """Binary label: 1 if any KDE-eligible crime occurred in this cell this week."""
    panel["label"] = (panel[count_cols].sum(axis=1) > 0).astype(int)
    prevalence = panel["label"].mean()
    logger.info(
        "label prevalence: %.1f%% positive (%d / %d rows)",
        prevalence * 100, panel["label"].sum(), len(panel),
    )
    return panel


# ── Label encoding for H3 cell IDs ───────────────────────────────────────────

def _encode_cells(panel: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]:
    """Replace H3 string cell IDs with integer indices for LightGBM.

    Returns:
        panel with added 'h3_cell_enc' integer column
        cell_encoder dict {h3_cell_str → int_index} for use at inference time
    """
    unique_cells = sorted(panel["h3_cell"].unique())
    cell_encoder = {cell: idx for idx, cell in enumerate(unique_cells)}
    panel["h3_cell_enc"] = panel["h3_cell"].map(cell_encoder)
    return panel, cell_encoder


# ── Public entry point ────────────────────────────────────────────────────────

def build_cell_features(snapshot_path: Path) -> Path:
    """Full pipeline: crimes Parquet → cell_features Parquet.

    Args:
        snapshot_path: Path to crimes_YYYY-MM-DD.parquet (from ingest.py)

    Returns:
        Path to the written cell_features_YYYY-MM-DD.parquet file.
    """
    date_str = snapshot_path.stem.replace("crimes_", "")
    out_path = SNAPSHOT_DIR / f"cell_features_{date_str}.parquet"

    logger.info("loading snapshot: %s", snapshot_path)
    df = pd.read_parquet(snapshot_path)

    # Convert effective_date to datetime if stored as object/string
    df["effective_date"] = pd.to_datetime(df["effective_date"], errors="coerce")

    crime_df = _filter_crimes(df)
    crime_df = _assign_cells(crime_df)

    panel = _build_panel(crime_df)
    panel, count_cols = _add_crime_counts(panel, crime_df)
    panel = _add_rolling_features(panel, count_cols)
    panel = _add_neighbour_density(panel)
    panel = _add_temporal_features(panel)
    panel = _add_label(panel, count_cols)
    panel, cell_encoder = _encode_cells(panel)

    # Save cell encoder alongside the parquet for use at inference time
    import pickle
    encoder_path = SNAPSHOT_DIR / f"cell_encoder_{date_str}.pkl"
    with open(encoder_path, "wb") as f:
        pickle.dump(cell_encoder, f)
    logger.info("cell encoder saved: %s (%d cells)", encoder_path, len(cell_encoder))

    panel.to_parquet(out_path, index=False)
    logger.info(
        "cell features saved: %s  (%d rows, %d cols)",
        out_path, len(panel), len(panel.columns),
    )
    return out_path


# ── CLI ───────────────────────────────────────────────────────────────────────

def _latest_snapshot() -> Path:
    snapshots = sorted(SNAPSHOT_DIR.glob("crimes_*.parquet"))
    if not snapshots:
        raise FileNotFoundError(
            f"No crimes_*.parquet files in {SNAPSHOT_DIR}. "
            "Run `python -m ml.data.ingest` first."
        )
    return snapshots[-1]


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="Build H3 cell feature table")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--latest", action="store_true",
                       help="Use the most recent crimes_*.parquet snapshot")
    group.add_argument("--snapshot", type=Path,
                       help="Explicit path to a crimes_*.parquet file")
    args = parser.parse_args()

    snapshot = _latest_snapshot() if args.latest else args.snapshot
    build_cell_features(snapshot)

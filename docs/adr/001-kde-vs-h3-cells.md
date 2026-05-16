# ADR-001: KDE Risk Surface vs H3 Cell Grid

**Date:** 2026-05-14
**Status:** Accepted
**Deciders:** Sandip (sole developer)

---

## Context

The backend needs to assign a risk score to any arbitrary (lat, lng) point
along a route. Two main approaches were considered for v1.

At the time of the decision, the Cosmos DB had approximately 4,000–5,000 valid
Delhi-NCR crime records.

---

## Options considered

### Option A — H3 hexagonal cell grid (res 8, ~0.74 km²)

Pre-aggregate crime counts per H3 cell and train a classifier (e.g. LightGBM)
that predicts P(crime in cell next week) given historical density features.

**Pros:**
- Explicitly models temporal patterns (day-of-week, month, trend)
- Well-studied approach for urban crime prediction

**Cons:**
- Delhi-NCR at res 8 has ~2,800 cells. With ~4,000 records spread over 2 years,
  most cells have fewer than 2 crimes — most cells are empty.
- A classifier trained on mostly-empty cells learns "predict zero" as the
  dominant strategy. PR-AUC on sparse data approaches a trivial baseline.
- Empty cells return zero risk, so routes through genuinely dangerous-but-sparse
  areas are incorrectly rated "Low".

### Option B — Gaussian KDE on raw coordinates (chosen)

Fit a `scipy.stats.gaussian_kde` on the (lat, lng) coordinates of crime events.
The KDE produces a smooth continuous density surface queryable at any point.

**Pros:**
- No sparsity problem — KDE smooths over data points, so nearby crimes
  influence adjacent areas even with few records.
- Works at any resolution — query at a waypoint every 100m without binning.
- Simple to implement, interpret, and audit: `kde(lat, lng)` returns a number.
- Recency weighting via `weight = exp(-age_days / 90)` is trivially added at
  fit time.

**Cons:**
- Does not model temporal patterns within training data (hour of day, day of
  week) — handled separately via a hand-tuned time multiplier (see ADR-003).
- Assumes crime events are drawn from a stationary spatial process; does not
  capture trend or seasonality.
- Bandwidth selection (Silverman's rule × 0.5) is a heuristic, not data-driven.

---

## Decision

Use **Option B (KDE)** for v1. The data volume (~4,000 KDE-eligible records)
is insufficient for reliable cell-level classification. KDE gives a smooth,
queryable risk surface with no empty-cell artefacts.

Upgrade path: Phase 4 adds LightGBM at H3 res 7 (~5 km² cells, ~350 cells
over Delhi-NCR) once data volume reaches a level where cells are meaningfully
populated. The `USE_LIGHTGBM` feature flag enables this as an additive ensemble
without replacing KDE.

---

## Consequences

- `ml/train_kde.py` trains one `FixedBandwidthKDE` per crime macro category.
- `backend/app/services/risk_model.py` scores waypoints by evaluating the KDE
  at each (lat, lng) and summing across categories with female-safety weights.
- Banding thresholds (Low/Medium/High) are calibrated from scoring 400 random
  Delhi points with the trained KDE — not from theoretical percentiles.
- Tech debt: no hour-of-day signal in training data. Tracked in CLAUDE.md §Tech Debt #1.

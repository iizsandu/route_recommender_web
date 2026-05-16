# ADR-003: Hand-Tuned Time-of-Day Multiplier

**Date:** 2026-05-14
**Status:** Accepted (revisit in Phase 4 when hour-of-day data is available)
**Deciders:** Sandip (sole developer)

---

## Context

Crime risk varies significantly by time of day — streets that are safe at noon
may be dangerous at 2 AM. The backend needs to adjust risk scores based on
the user's departure time.

The training dataset (crime records extracted from news articles) **does not
reliably include hour-of-day**. Only ~20% of records have a parseable crime time;
the rest carry only a date.

---

## Options considered

### Option A — Train time-of-day into the KDE model

Fit a 3D KDE over (lat, lng, hour_of_day). At query time, evaluate the KDE at
(lat, lng, query_hour).

**Pros:**
- Learned from data — captures the actual temporal distribution of crimes.
- No hand-tuning required.

**Cons:**
- Only ~20% of records have hour_of_day. Training a 3D KDE on 20% of the data
  (≈800 records) while ignoring the other 80% introduces severe selection bias.
  Records with parseable times skew toward high-profile cases covered in detail,
  not representative of all crimes.
- 3D KDE with a very sparse third dimension (hour) produces near-uniform
  marginal distributions in the time axis — the model effectively learns nothing
  about temporal patterns.

### Option B — NCRB aggregate statistics lookup

Use National Crime Records Bureau (NCRB) published statistics on time-of-day
crime distribution (India-wide) as a prior, and scale KDE scores by the
hour-bucket probability from NCRB data.

**Pros:**
- Data-driven at the aggregate level.
- Consistent with official government statistics.

**Cons:**
- NCRB time-of-day breakdowns are published for broad crime categories, not the
  specific female-safety categories used in this project.
- NCRB data is India-wide; Delhi-NCR patterns may differ significantly.
- Requires parsing and maintaining NCRB PDFs — significant engineering overhead
  for uncertain signal quality.

### Option C — Hand-tuned multiplier bands (chosen)

Apply a scalar multiplier to the KDE score based on which time band the
waypoint's estimated arrival falls into:

| Band | Hours | Multiplier | Rationale |
|---|---|---|---|
| Night | 22:00–05:00 | 2.5× | Consistent with global crime research: fewer people → higher per-person risk |
| Evening | 18:00–22:00 | 1.5× | Reduced visibility, commute end, higher street crime |
| Morning rush | 05:00–09:00 | 1.0× | Baseline — crowds provide informal safety |
| Daytime | 09:00–18:00 | 0.7× | Maximum crowds, businesses open, lowest risk |

**Pros:**
- Transparent and auditable — the multiplier is a config value, not a black box.
- Directionally consistent with published criminology research.
- Applied at query time, not at training time — no data leakage, no retraining
  needed when multipliers are recalibrated.
- Works correctly for zero hour-of-day training data.

**Cons:**
- Not learned from Delhi-NCR crime data — may be miscalibrated for local patterns.
- Four coarse bands lose within-band variation (e.g. 22:30 vs 04:30 get same multiplier).

---

## Decision

Use **Option C (hand-tuned multiplier)** for v1. The data constraints make
Options A and B unreliable. A transparent, config-driven multiplier is better
than a poorly-calibrated data-driven one.

The multipliers are stored in `_TIME_BANDS` in `backend/app/services/risk_model.py`
and can be updated without retraining the model.

---

## Consequences

- `_time_modifier(hour)` is a pure function applied per waypoint at query time.
  The waypoint's estimated arrival time (`depart_time + eta`) determines the
  band — routes that start at dusk but reach a distant waypoint after midnight
  correctly receive the night multiplier for that segment.
- Recalibration path: when the sister repo completes Phase 1.5 (re-extracting
  crime times from article text), re-evaluate Options A or B against the
  resulting hour-rich dataset. Track as Tech Debt #1 in CLAUDE.md.
- These multipliers are intentionally NOT exposed to the frontend — the user
  enters departure time, the backend applies the multiplier, and the band is
  returned. No raw multiplier values are surfaced to clients.

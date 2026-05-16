# ADR-002: 3-Band Risk Display vs Raw Scores

**Date:** 2026-05-14
**Status:** Accepted
**Deciders:** Sandip (sole developer)

---

## Context

The backend computes a continuous `route_score` (float) for each candidate route.
The question is what to return to the frontend and show to the user.

---

## Options considered

### Option A — Raw numerical score (e.g. "Risk score: 12.4 / 100")

Return the actual composite KDE score scaled to a 0–100 range.

**Pros:**
- Maximum information — users can distinguish between routes scored 12 and 14.
- Easier to build A/B tests and thresholds on.

**Cons (legal):**
- Publishing specific numerical risk scores for specific streets or neighbourhoods
  creates defamation liability under Indian law. A news article headline saying
  "Lajpat Nagar: risk score 87" could be actionable even if directionally correct.
- KDE on ~4,000 data points cannot justify two-decimal precision. False precision
  is misleading and undermines user trust if the model's calibration is off.

**Cons (UX):**
- Users making real-time travel decisions want an action ("take this route"),
  not a number to interpret. Research on risk communication consistently shows
  coarse categorical labels outperform numerical scores for decision support.

### Option B — 3-band categorical label: Low / Medium / High (chosen)

Map the continuous score to one of three bands using city-wide p33/p66
percentiles as thresholds.

**Pros:**
- Legally safer: coarse categories are harder to challenge as defamatory than
  specific numbers for specific locations.
- Honest about model uncertainty: with ~4,000 training points, a KDE cannot
  reliably distinguish a score of 0.12 from 0.15. The band says "these routes
  differ meaningfully" without overclaiming precision.
- Clear UX: green = Low, amber = Medium, red = High. No interpretation needed.

**Cons:**
- Loss of information within a band. Two routes scored 0.07 and 0.71 both show
  as "Medium" (if thresholds are 0.07 / 0.91). The safest route within a band
  is still returned first by sort order, even if the badge looks the same.
- Threshold drift: thresholds calibrated today may become miscalibrated if
  the score distribution shifts after a retrain.

---

## Decision

Use **Option B (3-band display)**. The legal and UX benefits outweigh the
information loss, especially at v1 data volumes where precision would be false
anyway.

The raw float score is:
- Computed server-side (needed for route ranking and logging).
- Logged to structlog for evaluation and monitoring.
- **Never** returned in the API response body.

---

## Consequences

- `RouteOption.risk_band` is typed `Literal["Low", "Medium", "High"]` — enforced
  at the Pydantic schema level, not just by convention.
- `BAND_LOW_THRESHOLD` and `BAND_HIGH_THRESHOLD` are config-driven (`.env`) and
  must be recalibrated after each model retrain.
- The `/routes/recommend` response deliberately omits `risk_score` as a field.
  Any future consumer wanting the raw score must be given explicit access via a
  separate authenticated endpoint (out of scope for v1).
- Disclaimer text (visible to users on first visit) must be reviewed by a lawyer
  before any marketing push. Tracked in CLAUDE.md §Tech Debt #8.

# Learning Log

---

## P1-3 — ml/train_kde.py (2026-05-14)

### Key ideas to retain
- `gaussian_kde` expects data shape `(dimensions, n_samples)` — DataFrame gives `(n, 2)`, must transpose with `.T`
- `bw_method=lambda k: k.silverman_factor() * 0.5` — the lambda gets the fitted KDE instance, so you can read its auto-computed Silverman factor and scale it down without recomputing manually
- Recency weights: `exp(-age_days / 90)`, then normalise so they sum to 1 — scipy requires normalised weights
- `fillna(today)` for missing dates: treats unknown-date crimes as maximally recent (conservative — safer than silently down-weighting)
- MLflow metric keys cannot contain spaces — replace with underscores before logging
- Log artifact AFTER writing the pkl — MLflow copies the file into its store; the local copy stays as a fast-access cache
- `ARTIFACTS_DIR` must be defined at module level before `run()` uses it as a default parameter — default parameter values are evaluated at definition time, not call time

### Bugs caught while typing
- `ARTIFACTS_DIR` constant missing — dropped between chunks, caused `NameError` at import time
- Missing blank lines between top-level functions (PEP 8: two blank lines required)

---

## P1-2 — ml/data/validate.py (2026-05-13)

### MCQ results (5 questions)
- Q1 B ✓ — ephemeral context; GitHub Actions runner is stateless, file context would fail
- Q2 B ✓ — `expect_column_values_to_be_in_set` on KNOWN_NON_UNKNOWN_MACROS with `mostly=0.70`
- Q3 B ✓ — write audit JSON before raising; the file is the diagnosis
- Q4 D ✗ → correct: B — `lat=0.0` is a real float outside [28, 29.5]; GE evaluates it, expectation fails
- Q5 B ✓ — `mostly` gives the observed percentage, distinguishing minor drift from extractor failure

### Key ideas to retain
- `discard_failed_expectations=False` is essential — default `True` silently removes failing expectations from the saved suite, meaning broken data teaches GE to stop checking itself.
- `frozenset - set` works in Python and returns a new `frozenset`. No cast needed.
- GE's bounds check (`expect_column_values_to_be_between`) evaluates every non-null value — `lat=0.0` is NOT skipped, it fails the check.
- Write audit JSON BEFORE raising — the file is the evidence engineers need to diagnose the failure.
- Constants belong at module top, not interleaved with functions. Python evaluates function bodies at call time so it won't crash, but it's fragile and confusing.

### Bugs caught while typing
- `LAT_MIN/LNG_MIN` constants placed after `validate()` — moved to module top.
- `import os` unused in `__main__` — removed.

---

## P1-1 — ml/data/ingest.py + category_mapping.py (2026-05-13)

### MCQ results (5 questions)
- Q1 A ✗ → correct: D — Cosmos is schemaless; `is_crime` may be bool, string, or int depending on extraction version
- Q2 C ✗ → correct: B — geocoding is a separate concern; null lat/lng records must be dropped, not imputed
- Q3 B ✓ — dict with lowercase keys is correct for O(1) lookup + casing normalisation
- Q4 D ✗ → correct: B — `pd.to_parquet()` silently overwrites existing files (no append, no error)
- Q5 A ✗ → correct: B — `pd.DataFrame(list[dict])` works natively; risk is all-None column gets `object` dtype

### Spaced repetition (P0-5 revisit)
- Q: why does module-level `Settings()` fail earlier than inside a function?
- Answer given: "because function needs to be called first" — directionally right, missing the consequence
- Correct: module-level = import time = before port bind = clear startup crash. Function-level = first request = server appears healthy, crashes on use. The failure *mode* is what matters.

### Key ideas to retain
- `Path(__file__).parent` anchors paths to the source file location, not the working directory. Use it for all data/artifact paths in ML scripts.
- `df.get("col")` vs `df["col"]`: the former returns `None` on missing column (safe); the latter raises `KeyError`.
- `pd.to_numeric(series, errors="coerce")` turns unparseable values → NaN. Always use this for lat/lng from external sources.
- `is_crime` normalisation pattern: `.astype(str).str.lower() == "true"` handles bool/int/string variants from schemaless Cosmos.
- Empty snapshot → raise, don't return. Silent empty file = corrupt model downstream.

### Bugs caught while typing
- `datetime` imported but unused — removed.

---

## P0-5 — Observability Basics (2026-05-12)

### MCQ results (5 questions)
- Q1 B ✓ — `merge_contextvars` pulls ContextVar into every log event automatically
- Q2 C ✓ — no fallback serializer → `TypeError` → log line silently lost
- Q3 B ✓ — `ContextVar` isolated per async task; global would collide across concurrent requests
- Q4 A ✗ → correct: C — `Settings()` at module level crashes at import time, not at first request
- Q5 A ✓ — processor pipeline: swap the renderer, change nothing at call sites

### Bugs caught while typing
- Typo: `congigure` instead of `configure` in main.py import
- Merged both middlewares into one `add_middleware` call — each needs its own call
- `ALLOWED_ORIGINS` in config.py missing type annotation and quotes (raw URL text = syntax error)

### Key ideas to retain
- Q4 revisit: module-level `Settings()` = fails at import = before port bind. Lazy init inside a function = fails at first use.
- `ContextVar` token pattern: `token = var.set(val)` → do work → `var.reset(token)`. The reset is essential in async servers where tasks are reused.

### Skipped
- Step 2 prediction pauses skipped by user request.

---

## P0-4 — Deploy Frontend to Vercel (2026-05-11)

### Concept MCQ results (5 questions)
- Q1 B ✓ — Vite strips non-`VITE_*` vars at build time; browser gets `undefined`
- Q2 C ✓ — Vercel atomic deploy: failed build cancels, old build stays live
- Q3 C ✗ → correct: B — `npm run build` checks compilation, NOT runtime API reachability
- Q4 A ✗ → correct: B — mixed content (HTTPS frontend + HTTP backend) blocks fetch regardless of CORS
- Q5 B ✓ — Vercel env var scopes (Production / Preview / Development) handle per-environment URLs

### Key ideas to retain
- `VITE_API_BASE_URL` must exist at *build time* — baked into the bundle, not read at runtime. A missing var means `undefined` in the browser.
- Local dev uses the vite.config.js proxy (`/api/health` → `localhost:8000/health`), so `VITE_API_BASE_URL` can be unset locally.
- The GitHub Actions CI workflow only proves the bundle compiles. Vercel's own build is what deploys.

### Skipped
- Step 2 guided walkthrough and Step 3 post-write quiz skipped by user request (protocol break confirmed).

---

## P0-2 — Cosmos DB Read-Only Client (2026-05-06)

### 3 things understood that weren't before

1. **Why async client construction is deferred to `connect()`** — `CosmosClient` opens an `aiohttp` session on instantiation, which requires a live event loop. `__init__` is synchronous; the event loop may not exist yet. `connect()` is called from FastAPI's `lifespan`, which runs inside the loop.

2. **Why `frozenset` for `_COSMOS_INTERNAL_FIELDS`** — `in` on a `frozenset` is O(1) average (hash lookup) vs O(n) for a list. Small win here (5 fields), but the pattern is correct for any membership test that runs per-document.

3. **Why `_ts` requires `int(since.timestamp())` not a string** — Cosmos stores `_ts` as a Unix epoch integer. String comparison against an integer field either fails silently or errors. Python's `datetime.timestamp()` returns a float; `int()` cast aligns with Cosmos's integer type.

### 1 thing not yet fully grasped

- **`enable_cross_partition_query=True`** — understood *that* it's required for `SELECT *`, but not yet clear on what "cross-partition" means in terms of Cosmos's physical storage model (how data is partitioned and why fan-out is expensive).

### 1 question answered wrong (must get right next time)

- **Chunk 3 prediction:** "What should the happy-path test assert?" — answered C ("verify mock was called") instead of B ("verify business fields present + metadata absent"). Lesson: test *behaviour* (output shape and content), not *implementation* (whether a mock was invoked).

### Skipped

- Step 3 Round A (conceptual MCQs) and Round B (FAANG interview questions) were skipped by user choice. Revisit Round A Q2 (naive datetime timezone assumption) and Q3 (correct RBAC role) next session.

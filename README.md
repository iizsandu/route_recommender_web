# Crime-Aware Route Recommender

Recommends the safest route between two points in Delhi-NCR for female commuters,
using historical crime data extracted by the sister repo and a KDE risk surface
trained weekly from ~9,000 Delhi-NCR crime records.

**Live demo:**
- Frontend: https://route-recommender-web.vercel.app
- Backend health: https://route-recommender-backend.whitecoast-8c771146.eastasia.azurecontainerapps.io/health
- API docs: https://route-recommender-backend.whitecoast-8c771146.eastasia.azurecontainerapps.io/docs

---

## How it works

```
Sister repo (LLM pipeline)
  └── Azure Cosmos DB  ←─────────────────────────────┐
                                                      │ read-only
Weekly retrain (GitHub Actions, Sunday 02:00 IST)    │
  ml/data/ingest.py     ← fetch ~9k crime records ───┘
  ml/data/validate.py   ← Great Expectations gate
  ml/train_kde.py       ← fit 8 per-category KDE models
  ml/evaluate.py        ← PR-AUC + recall@10% on holdout
  ml/promote_model.py   ← champion/challenger gate → MLflow registry
  ml/generate_heatmap.py← pre-compute static risk heatmap GeoJSON

Backend (FastAPI, Azure Container Apps)
  POST /routes/recommend
    ├── geocode addresses (ORS Pelias)
    ├── fetch candidate routes (OpenRouteService)
    ├── score each route (KDE density × crime weights × time modifier)
    └── return ranked Low / Medium / High bands

Frontend (React + MapLibre GL, Vercel)
  ├── MapView: routes coloured by risk band
  ├── RouteForm: origin / destination / departure time
  └── RouteResults: ranked list with risk badges
```

---

## Local development

### Prerequisites

- Python 3.11+
- Node.js 18+
- A `.env` file (copy from `.env.example` and fill in real keys)

### Backend

```powershell
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# From repo root (not backend/) so that ml/ is on the path:
cd ..
uvicorn backend.app.main:app --reload --port 8000 --app-dir backend
# OR from backend/:
cd backend
uvicorn app.main:app --reload --port 8000
```

Endpoints:
- `GET  /health`            — liveness check
- `GET  /metrics`           — Prometheus metrics (routes_recommended_total, model_inference_seconds)
- `POST /routes/recommend`  — main routing endpoint
- `GET  /risk/heatmap`      — pre-computed risk heatmap GeoJSON
- `GET  /docs`              — interactive API docs (Swagger UI)

### Frontend

```powershell
cd frontend
npm install
npm run dev          # http://localhost:3000
npm run build        # production build check
```

### Running both with Docker

```powershell
cp .env.example .env   # fill in COSMOS_CONNECTION_STRING, ORS_API_KEY, VITE_MAPTILER_KEY
docker compose up --build
```

---

## ML pipeline

All scripts run from **repo root** (not from `ml/`).

### One-time setup

```powershell
pip install -r ml/requirements.txt
```

### Full pipeline (matches weekly GitHub Action)

```powershell
# 1. Ingest from Cosmos DB (or local JSON for dev)
python -m ml.data.ingest                                      # from Cosmos
python -m ml.data.ingest --from-json ml/data/data.json        # local dev

# 2. Validate snapshot
python -m ml.data.validate ml/data/snapshots/crimes_YYYY-MM-DD.parquet

# 3. Build H3 cell features (for LightGBM)
python -m ml.data.h3_cells --latest

# 4. Train KDE models (8 per-category pkl files → ml/artifacts/)
python -m ml.train_kde --latest

# 5. Train LightGBM models (optional; requires USE_LIGHTGBM=True to activate)
python -m ml.train_lightgbm --latest

# 6. Evaluate (PR-AUC + recall@10% on 30-day holdout)
python -m ml.evaluate ml/data/snapshots/crimes_YYYY-MM-DD.parquet ml/artifacts

# 7. Champion/challenger gate → MLflow registry
python -m ml.promote_model ml/data/snapshots/crimes_YYYY-MM-DD.parquet ml/artifacts

# 8. Generate risk heatmap
python -m ml.generate_heatmap
```

### Browsing MLflow runs

```powershell
mlflow ui --backend-store-uri sqlite:///ml/artifacts/mlruns.db
# open http://localhost:5000
```

---

## Environment variables

Copy `.env.example` to `.env`. All variables are documented there. Required variables
(backend refuses to start without them):

| Variable | Description |
|---|---|
| `COSMOS_CONNECTION_STRING` | Azure Cosmos DB connection string (read-only) |
| `ORS_API_KEY` | OpenRouteService API key |
| `KDE_ARTIFACTS_DIR` | Path to `ml/artifacts/` (contains `kde_*.pkl`) |

Key optional variables:

| Variable | Default | Description |
|---|---|---|
| `USE_LIGHTGBM` | `False` | Enable KDE + LightGBM ensemble |
| `VITE_SENTRY_DSN` | _(empty)_ | Sentry DSN for frontend error tracking |
| `HEATMAP_PATH` | `ml/artifacts/heatmap.geojson` | Pre-computed heatmap |
| `LOG_FORMAT` | `console` | `json` in production (Azure), `console` locally |

---

## Deployment

### Backend → Azure Container Apps

The GitHub Actions workflow (`.github/workflows/backend-deploy.yml`) builds the
Docker image, pushes to GitHub Container Registry, and prints the deploy command.
Run the deploy manually from your machine:

```powershell
.\scripts\deploy.ps1
```

> **Note:** Automated Azure deploy is disabled on the student account (Entra ID
> app registration is blocked). The workflow builds and smoke-tests the image;
> you deploy with `deploy.ps1` after CI passes.

### Frontend → Vercel

Vercel auto-deploys on every push to `master`. Set these environment variables
in the Vercel project dashboard:

| Variable | Scope |
|---|---|
| `VITE_API_BASE_URL` | Production, Preview |
| `VITE_MAPTILER_KEY` | Production, Preview |
| `VITE_SENTRY_DSN` | Production |

### Weekly retrain → GitHub Actions

`.github/workflows/retrain-weekly.yml` runs every Sunday 02:00 IST automatically.
Trigger manually via Actions → Weekly Retrain → Run workflow.

Required secret: `COSMOS_CONNECTION_STRING`
Optional secret: `SLACK_WEBHOOK` (Slack notifications on success/failure)

---

## Observability

| Signal | Where |
|---|---|
| Structured logs (JSON) | Azure Container Apps log stream; every request logs `duration_ms` |
| Prometheus metrics | `GET /metrics` — `routes_recommended_total`, `model_inference_seconds` |
| Frontend errors | Sentry (configure `VITE_SENTRY_DSN` in Vercel) |

---

## Architecture decisions

See [`docs/adr/`](docs/adr/) for the reasoning behind key design choices:

- [ADR-001](docs/adr/001-kde-vs-h3-cells.md) — KDE risk surface vs H3 cell grid
- [ADR-002](docs/adr/002-three-band-display.md) — 3-band risk display vs raw scores
- [ADR-003](docs/adr/003-time-multiplier.md) — Hand-tuned time-of-day multiplier

---

## Sister repo

`route_recommender_second` runs an LLM pipeline that reads news articles, extracts
crime events, and writes structured records to Azure Cosmos DB. This repo is
**read-only** against that database — no writes, no ETL duplication.

---

## Project status

| Phase | Status |
|---|---|
| P0 Bootstrap | ✅ Complete |
| P1 Risk Surface MVP | ✅ Complete |
| P2 Frontend MVP | ✅ Complete |
| P3 MLOps Foundation | ✅ Complete |
| P4 LightGBM | ✅ Pipeline built (activate with `USE_LIGHTGBM=True`) |
| P5 Productionisation | ✅ Complete |
| P4 LightGBM (data gate) | ⏳ Need ≥15k records for full activation |

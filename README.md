# 🌊 Bio-SentinelX — Urban Flood Prediction & Early-Warning API
[DeepWiki](https://deepwiki.com/gaur-avvv/Flood-Prediction-Early-Warning)

**GIS-integrated machine-learning engine for hyper-local urban flood forecasting, micro-hotspot mapping, and ward-level readiness scoring — built for the Indian monsoon context.**

[![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111%2B-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![scikit-learn](https://img.shields.io/badge/scikit--learn-1.4%2B-F7931E?logo=scikit-learn&logoColor=white)](https://scikit-learn.org/)
[![XGBoost](https://img.shields.io/badge/XGBoost-2.0%2B-006ACC)](https://xgboost.readthedocs.io/)
[![LightGBM](https://img.shields.io/badge/LightGBM-4.3%2B-02569B)](https://lightgbm.readthedocs.io/)
[![Docker](https://img.shields.io/badge/Docker-ready-2496ED?logo=docker&logoColor=white)](https://www.docker.com/)
[![Deploy on Railway](https://img.shields.io/badge/Deploy-Railway-0B0D0E?logo=railway&logoColor=white)](https://railway.app/)
[![Deploy on Render](https://img.shields.io/badge/Deploy-Render-46E3B7?logo=render&logoColor=111111)](https://render.com/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](#-license)

---

## 📖 Overview

https://flood-prediction-early-warning.onrender.com/docs

<img width="1528" height="861" alt="image" src="https://github.com/user-attachments/assets/f6b6c614-009c-46ac-8d67-923864d1385f" />


**Bio-SentinelX** is a FastAPI backend that predicts urban flooding at hyper-local grid resolution (down to **250m–1km cells**), identifies **2,500+ micro-hotspots** across a city, and produces **ward-level Pre-Monsoon Readiness Scores** (A–D) so disaster-response teams (e.g. NDRF/SDRF) can pre-position resources before the monsoon hits.

It fuses **free, open geospatial and weather data** (no paid satellite/radar feeds) with a **stacked machine-learning ensemble** and classical hydrology formulas to deliver:

- Single-point and bulk flood-risk predictions
- City-wide micro-hotspot scans
- Ward-level readiness scoring for pre-monsoon planning
- Real-time nowcasts (30–120 minutes ahead)
- Automated email alerts for high-risk wards, hotspots, and nowcasts
- Nightly model retraining and hourly data refresh via background scheduler

> **Repo:** [gaur-avvv/Flood-Prediction-Early-Warning](https://github.com/gaur-avvv/Flood-Prediction-Early-Warning)

---

## 🏗️ Architecture

```mermaid
flowchart TD
    subgraph EXT["🌐 Free External Data APIs"]
        A1[Open-Meteo<br/>rainfall · temp · humidity · wind · soil moisture]
        A2[Open-Meteo Flood API<br/>GloFAS river discharge]
        A3[OpenTopoData<br/>SRTM 30m elevation · slope · curvature]
        A4[SoilGrids REST<br/>soil type · clay % · drainage proxy]
        A5[OpenStreetMap Overpass<br/>drainage lines · pump stations]
    end

    subgraph COLLECT["services/data_collector.py"]
        B1[DataCollector]
        B2[Synthetic monsoon-pattern<br/>fallback generator]
    end

    subgraph FEATURES["services/feature_engineering.py"]
        C1["44 engineered features:<br/>rolling rainfall (1–72h) · antecedent<br/>precipitation index · discharge anomaly ·<br/>elevation/slope · impervious % ·<br/>drainage capacity · population density"]
    end

    subgraph MODEL["models/flood_model.py"]
        D1[Stacked Ensemble<br/>RF + XGBoost + LightGBM]
        D2[Meta-learner:<br/>Logistic Regression]
        D3[Calibrated probabilities<br/>CalibratedClassifierCV]
        D4[Depth Regressor +<br/>SCS rational runoff fallback]
    end

    subgraph TRAIN["services/trainer.py"]
        E1[ModelTrainer<br/>auto-init · nightly retrain]
    end

    subgraph PREDICT["services/predictor.py"]
        F1[Single-point risk<br/>SAFE → CRITICAL]
        F2[Bulk / grid<br/>hotspot scanning]
        F3[Ward Readiness<br/>Scores A–D]
        F4[Nowcast<br/>30–120 min]
    end

    subgraph API["main.py — FastAPI"]
        G1["/train · /predict · /predict/bulk<br/>/hotspots · /wards/readiness<br/>/nowcast · /data/ingest · /email/*"]
    end

    subgraph STORE["database/"]
        H1[(SQLite / PostgreSQL<br/>via SQLAlchemy async)]
    end

    subgraph ALERTS["services/email_service.py"]
        I1[SMTP Email Alerts]
    end

    subgraph SCHED["APScheduler"]
        J1[Nightly retrain 02:00 UTC]
        J2[Hourly data sync]
    end

    A1 --> B1
    A2 --> B1
    A3 --> B1
    A4 --> B1
    A5 --> B1
    B1 -.fallback.-> B2
    B1 --> C1
    C1 --> D1
    D1 --> D2
    D2 --> D3
    D3 --> D4
    E1 --> D1
    D4 --> F1
    D4 --> F2
    D4 --> F3
    D4 --> F4
    F1 --> G1
    F2 --> G1
    F3 --> G1
    F4 --> G1
    G1 <--> H1
    G1 --> I1
    J1 --> E1
    J2 --> B1
```

---

## ✨ Features

| Capability | Endpoint | Description |
|---|---|---|
| **Single-point prediction** | `POST /predict` | Flood probability + inundation depth for one lat/lon, factoring rainfall, elevation, slope, soil moisture, drainage, LULC, and antecedent precipitation. |
| **Bulk prediction** | `POST /predict/bulk` | Batch-predicts up to 500 locations in one call. |
| **Micro-hotspot scanning** | `GET /hotspots` | Grid-scans a city (0.25–2 km cells) and returns every cell above a risk threshold. |
| **Ward readiness scoring** | `GET /wards/readiness` | A–D readiness grade per ward based on predicted depth, drainage health, and infrastructure exposure. |
| **Nowcasting** | `GET /nowcast` | 30–120 minute short-range flood forecast. |
| **Email alerting** | `POST /email/*` | Sends SMTP alerts for high-risk wards, hotspots, or nowcasts. |
| **Auto-retraining** | background scheduler | Retrains nightly (02:00 UTC) and refreshes source data hourly. |
| **Auto-init on boot** | `main.py` lifespan | Trains a model automatically on first startup if none exists. |

---

## 🧰 Tech Stack

| Layer | Technology |
|---|---|
| **API framework** | FastAPI + Uvicorn (`--workers`, async lifespan, CORS) |
| **ML models** | scikit-learn (Random Forest, `StackingClassifier`, `CalibratedClassifierCV`), XGBoost, LightGBM |
| **Data processing** | pandas, numpy, scipy, joblib |
| **Database** | SQLAlchemy 2.0 (async) — SQLite (`aiosqlite`) locally, PostgreSQL (`asyncpg`) in production |
| **Scheduling** | APScheduler (`AsyncIOScheduler`) — cron + interval jobs |
| **Validation** | Pydantic v2 schemas (`models/schemas.py`) |
| **Email** | SMTP (`services/email_service.py`) |
| **Logging** | `python-json-logger` |
| **Containerization** | Docker (multi-stage build, non-root user, healthcheck) |
| **Deployment** | Railway or Render (`railway.toml`, `render.yaml`, `nixpacks.toml`, `Procfile`) |

---

## 🚀 Setup & Installation

### Prerequisites
- Python 3.11+
- pip
- (Optional) Docker, if you prefer containerized setup

### 1. Clone the repo

```bash
git clone https://github.com/gaur-avvv/Flood-Prediction-Early-Warning.git
cd Flood-Prediction-Early-Warning
```

### 2. Create a virtual environment

```bash
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

Copy `.env.example` to `.env` and adjust as needed:

```bash
cp .env.example .env
```

| Variable | Default / Example | Notes |
|---|---|---|
| `DATABASE_URL` | `sqlite+aiosqlite:///./flood_data.db` | Swap to `postgresql+asyncpg://user:password@host:5432/dbname` for production (Railway injects this automatically when you add its Postgres plugin). |
| `LOG_LEVEL` | `INFO` | Logging verbosity. |
| `PORT` | `8000` | App port (overridden by Railway's `$PORT` at runtime). |
| `GOOGLE_EE_SERVICE_ACCOUNT` / `GOOGLE_EE_PRIVATE_KEY` | — | Optional, only needed if you extend the collector with Google Earth Engine LULC/NDVI data. |

> All core data sources (Open-Meteo, Open-Meteo Flood/GloFAS, OpenTopoData, SoilGrids, OSM Overpass) are **free and require no API key**.

For email alerts, also set SMTP credentials (host, port, from-address, recipients) as read by `services/email_service.py` — check `GET /email/config` after startup to confirm they're picked up correctly.

### 5. Run locally

```bash
uvicorn main:app --reload
```

The API boots at `http://localhost:8000`. On first startup it auto-initializes a model if none exists, and schedules:
- **Nightly retraining** — 02:00 UTC
- **Hourly data sync** — `data_collector.sync_latest_observations`

Interactive API docs are available at:
- Swagger UI → `http://localhost:8000/docs`
- ReDoc → `http://localhost:8000/redoc`

### 6. Run with Docker

```bash
docker build -t bio-sentinelx .
docker run -p 8000:8000 --env-file .env bio-sentinelx
```

The image is a multi-stage build (build deps stripped from the runtime layer), runs as a non-root user, and ships with a built-in `HEALTHCHECK` against `/health`.

### 7. Deploy to Railway

The repo is pre-configured for one-click Railway deployment via `railway.toml` + `nixpacks.toml` + `Procfile`:

```bash
web: uvicorn main:app --host 0.0.0.0 --port $PORT --workers 2 --loop asyncio
```

Add a Railway Postgres plugin to get `DATABASE_URL` injected automatically for production-grade storage.

### 8. Deploy to Render

The repository includes `render.yaml` for a Docker-based Render web service and a managed PostgreSQL database. To deploy:

1. Push this repository to GitHub.
2. In Render, select **New → Blueprint** and choose this repository.
3. Review the generated web service and PostgreSQL database, then click **Apply**.
4. Open the generated service URL and verify `/health`, `/docs`, and `/redoc`.

Render supplies the `PORT` variable automatically. The Blueprint supplies `DATABASE_URL` from PostgreSQL, so training data and location records are not stored in an ephemeral SQLite file. The Docker image starts with one Uvicorn worker and exposes `/health` for Render health checks. Initial model training can take several minutes because it fetches historical data from external services; keep the health-check grace period enabled during the first deployment.

> Render is a persistent web-service deployment and is preferred over serverless platforms for this application because the scheduler, background training, database sessions, and saved model files require a long-running process.

---

## 📡 API Documentation

Base URL (local): `http://localhost:8000`

### System

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Health check — model training status, accuracy, last-trained timestamp, hotspot count. |

```json
// GET /health → 200
{
  "status": "healthy",
  "model_trained": true,
  "model_accuracy": 0.91,
  "last_trained": "2026-08-01T02:00:00Z",
  "hotspots_mapped": 2531,
  "version": "2.0.0"
}
```

### Training

| Method | Path | Description |
|---|---|---|
| `POST` | `/train` | Queue model training for a location (background task). |
| `GET` | `/train/status` | Current training job status and metrics. |

```json
// POST /train
{
  "latitude": 19.0760,
  "longitude": 72.8777,
  "radius_km": 15.0,
  "years_back": 5
}
```

```json
// 200
{ "status": "queued", "message": "Training queued for (19.076, 72.8777) radius=15.0km, history=5y" }
```

### Prediction

| Method | Path | Description |
|---|---|---|
| `POST` | `/predict` | Single-location flood probability + depth. Requires a trained model (503 otherwise). |
| `POST` | `/predict/bulk` | Batch prediction for up to 500 locations. |
| `GET` | `/nowcast` | 30–120 min short-range forecast. |

```json
// POST /predict
{ "latitude": 19.0760, "longitude": 72.8777 }
```

```
GET /predict/bulk   (body: { "locations": [ {lat, lon}, ... up to 500 ] })
GET /nowcast?lat=19.0760&lon=72.8777&horizon_minutes=45
```

### Analysis

| Method | Path | Description |
|---|---|---|
| `GET` | `/hotspots` | Grid-scan for micro-hotspots. Params: `lat`, `lon`, `radius_km` (default 10), `grid_size_km` (default 1.0, 0.25–2), `min_risk` (default 0.5). |
| `GET` | `/wards/readiness` | Ward-level A–D readiness scores. Params: `lat`, `lon`, `radius_km` (default 15). |

```
GET /hotspots?lat=19.0760&lon=72.8777&radius_km=10&grid_size_km=1.0&min_risk=0.5
GET /wards/readiness?lat=19.0760&lon=72.8777&radius_km=15
```

### Data

| Method | Path | Description |
|---|---|---|
| `POST` | `/data/ingest` | Queue historical data ingestion (rainfall, DEM, LULC, soil) for a location. |
| `GET` | `/data/summary` | Data availability summary for a location. Params: `lat`, `lon`, `radius_km` (default 10). |

### Email Alerts

| Method | Path | Description |
|---|---|---|
| `GET` | `/email/config` | Check SMTP configuration status and default recipients. |
| `POST` | `/email/ward-alert` | Compute ward readiness and email results. Params: `lat`, `lon`, `radius_km` (default 15). |
| `POST` | `/email/hotspot-alert` | Scan hotspots and email critical results. Params: `lat`, `lon`, `radius_km` (default 10), `grid_size_km` (default 1.0), `min_risk` (default 0.5). |
| `POST` | `/email/nowcast-alert` | Run a nowcast and email it if risk exceeds the alert threshold. Params: `lat`, `lon`, `horizon_minutes` (default 45). |

```json
// POST /email/ward-alert body
{ "location": "Mumbai", "recipients": ["ops@example.com"] }
```

> Full interactive request/response schemas (from `models/schemas.py`) are always available live at `/docs` (Swagger) once the server is running.

---

## 🧪 Verification Results

The repository was cloned and tested with Python 3.14 in an isolated virtual environment. The comprehensive verification suite completed **114 passed, 0 failed** checks, covering model construction, training, feature engineering, prediction, database initialization, data fallbacks, hotspot scanning, ward readiness, nowcasting, and FastAPI endpoints.

### Model and metric results

| Metric | Result |
|---|---:|
| Accuracy | 0.9945 |
| F1 score | 0.9917 |
| ROC-AUC | 0.9984 |
| Precision | 0.9925 |
| Recall | 0.9910 |
| Depth MAE | 0.0089 m |

Confusion matrix from the independent test run:

```text
[[1328, 5],
 [6, 661]]
```

The verified model stack contains Random Forest, XGBoost, LightGBM, a Logistic Regression meta-learner, calibrated probabilities, and a separate inundation-depth regressor. Feature engineering currently produces **44 features**, including river-discharge features.

### Important evaluation limitations

- The repository's training metrics are calculated in-sample; the training code does not report a held-out test score.
- The test suite's second evaluation set is synthetic and should not be treated as real-world validation.
- When historical flood observations are unavailable, labels are generated by rules from rainfall, drainage, soil saturation, and terrain values.
- No real dataset files are included in the repository; external APIs and synthetic fallbacks provide training data.
- Confusion matrix, precision, and recall are not currently stored in the application's training metadata or API response.
- `india_wards.csv` is absent, so ward analysis falls back to generated ward names and grid locations.
- The `TestClient` dependency stack currently emits a Starlette/httpx deprecation warning, but endpoint behavior passed.

These results demonstrate that the software pipeline runs successfully. They do **not** establish operational life-safety accuracy. Real labeled flood events, temporal/geographic holdout evaluation, calibration checks, threshold analysis, and independent hydrological validation are required before operational use.

---

## 🔬 Scientific Basis / How It Works

Bio-SentinelX isn't built on a single published paper — it's an engineering combination of established hydrology methods and a standard tabular ML ensemble, fed entirely by free open data:

1. **Hydrology foundations**
   - **SCS (Soil Conservation Service) rational runoff method** — used as a physics-based fallback/blend for inundation-depth estimation when the ML regressor needs grounding.
   - **Antecedent Precipitation Index (API)** — captures how saturated the ground already is before a new rainfall event, a key driver of flash flooding.
   - **GloFAS river discharge anomaly** — flags river conditions materially above/below seasonal norms.

2. **Feature engineering** (44 features): rolling rainfall sums (1h–72h), API, discharge anomaly ratio, elevation/slope/curvature and flow accumulation (from SRTM 30m DEM), soil moisture and clay-derived drainage proxy, impervious surface percentage, drainage-network proximity and pump-station presence (OSM), population/building density, and a composite risk index.

3. **Machine learning model**: a **stacked ensemble** — Random Forest, XGBoost, and LightGBM as base learners, combined by a **Logistic Regression meta-learner** (`StackingClassifier`), with output probabilities calibrated via `CalibratedClassifierCV`. Dual outputs: a classifier for flood/no-flood (~10cm threshold) and a regressor for inundation depth in metres.

4. **Labelling**: where no historical ground-truth flood records exist for a location, the trainer self-generates rule-based synthetic labels from monsoon rainfall patterns, so the model can bootstrap in data-sparse cities.

5. **Data sources are all free/open** — Open-Meteo, Open-Meteo Flood API (GloFAS), OpenTopoData (SRTM), SoilGrids, and OpenStreetMap Overpass — deliberately avoiding paid satellite/radar feeds so the system stays deployable anywhere without licensing costs.

---

## 🤝 Contributing

Contributions are welcome:

1. Fork the repo and create a feature branch.
2. Keep new data sources free/no-key where possible, consistent with the project's design.
3. Add or update Pydantic schemas in `models/schemas.py` for any new endpoint.
4. Open a pull request describing the change and its impact on prediction accuracy or API surface.

---

## 📄 License

No `LICENSE` file is currently present in the repository. The badge above assumes **MIT** as a placeholder — add a `LICENSE` file to the repo root to make this explicit and enforceable.

---

## ⚠️ Disclaimer

This system is a decision-support tool for disaster-preparedness planning. It is **not** a certified early-warning system for life-safety use and should be used alongside official agency guidance (e.g. NDRF/SDRF, IMD) — not as a replacement for it.

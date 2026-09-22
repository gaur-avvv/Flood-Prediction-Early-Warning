"""
Bio-SentinelX Urban Flood Prediction API
GIS-integrated ML system for 2500+ micro-hotspot identification
Real-time training + prediction with ward-level Pre-Monsoon Readiness Scores
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import List, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import APIRouter, FastAPI, BackgroundTasks, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException

from database.db import init_db, get_session
from models.flood_model import get_model
from models.schemas import (
    LocationQuery,
    PredictionRequest,
    PredictionResponse,
    TrainingRequest,
    TrainingStatusResponse,
    WardReadinessResponse,
    MicroHotspotResponse,
    BulkPredictionRequest,
    BulkPredictionResponse,
    HealthResponse,
    EmailAlertRequest,
    EmailAlertResponse,
    EmailConfigResponse,
    ReadyResponse,
    EnrichedPredictionResponse,
    DriverContribution,
    FieldProvenanceModel,
)
from services.data_collector import DataCollector
from services.trainer import ModelTrainer
from services.predictor import FloodPredictor
from services.enrichment import get_enrichment_service, h3_index_for, H3_RESOLUTION
from services.email_service import (
    send_ward_alert,
    send_hotspot_alert,
    send_nowcast_alert,
    is_email_configured,
    SMTP_HOST,
    SMTP_FROM,
    ALERT_RECIPIENTS,
)
from security.auth import AuthRateLimitMiddleware, get_auth_config
from utils.errors import (
    APIError,
    api_error_handler,
    http_exception_handler,
    validation_exception_handler,
    unhandled_exception_handler,
)
from utils.request_id import RequestIDMiddleware
from utils.scheduler_lock import SchedulerLock

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# â”€â”€â”€ Globals â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
data_collector = DataCollector()
model_trainer = ModelTrainer()
flood_predictor = FloodPredictor()
scheduler = AsyncIOScheduler()
_scheduler_lock = SchedulerLock()

# Keep a reference so we can cancel / await during graceful shutdown
_init_task: Optional[asyncio.Task] = None  # type: ignore[assignment]


# â”€â”€â”€ Lifespan â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
@asynccontextmanager
async def lifespan(app: FastAPI):
    global _init_task

    logger.info("ðŸš€ Starting Bio-SentinelX Flood Prediction APIâ€¦")

    # T-29: security startup checks â€“ production refuses to boot without keys.
    auth_cfg = get_auth_config()
    if auth_cfg.production and not auth_cfg.keys:
        raise RuntimeError(
            "FLOOD_ENV=production requires FLOOD_API_KEYS to be configured."
        )
    if not auth_cfg.enabled:
        logger.warning("âš ï¸  API auth DISABLED (dev mode) â€“ set FLOOD_API_KEYS to enable.")

    await init_db()

    # Auto-train on startup if no model exists â€“ store the task so we can
    # await / cancel it cleanly on shutdown instead of being killed mid-train.
    _init_task = asyncio.create_task(
        model_trainer.auto_initialize(), name="auto_initialize"
    )

    # T-31: single-scheduler leader election â€“ only the lock holder runs jobs.
    leader = await _scheduler_lock.acquire()
    app.state.scheduler_leader = leader
    if leader:
        scheduler.add_job(model_trainer.scheduled_retrain, "cron", hour=2, minute=0)
        scheduler.add_job(data_collector.sync_latest_observations, "interval", hours=1)
        scheduler.add_job(_scheduler_lock.renew, "interval", seconds=60)
        scheduler.start()
        logger.info("â° Scheduler started (leader): nightly retrain + hourly data sync")
    else:
        logger.info("â¸ï¸  Scheduler standby â€“ another instance holds the leader lock")

    yield

    # â”€â”€ Graceful shutdown â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if scheduler.running:
        scheduler.shutdown(wait=False)
    logger.info("ðŸ›‘ Scheduler stopped")
    await _scheduler_lock.release()

    if _init_task is not None and not _init_task.done():
        logger.info(
            "â³ Waiting for background training to finish (max 10 min)â€¦"
        )
        try:
            await asyncio.wait_for(_init_task, timeout=600)
            logger.info("âœ… Background training completed before shutdown")
        except asyncio.TimeoutError:
            logger.warning(
                "âš ï¸  Training did not finish within shutdown window â€“ cancelling"
            )
            _init_task.cancel()
            try:
                await _init_task
            except (asyncio.CancelledError, Exception):
                pass
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.error("Training task raised during shutdown: %s", exc)


# â”€â”€â”€ App â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
APP_VERSION = "2.1.0"

app = FastAPI(
    title="Bio-SentinelX Urban Flood Prediction API",
    description=(
        "GIS-integrated ML engine for urban flood micro-hotspot identification. "
        "Identifies 2,500+ micro-hotspots, generates ward-level Pre-Monsoon "
        "Readiness Scores, and supports real-time nowcasting (30â€“45 min ahead). "
        "Canonical routes are versioned under /v1; legacy unversioned paths are "
        "deprecated (Sunset 2026-09-30)."
    ),
    version=APP_VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# â”€â”€â”€ CORS (T-29): env-driven allow-list; no wildcard with credentials â”€â”€â”€â”€â”€â”€â”€â”€â”€
_cors_raw = os.getenv("FLOOD_CORS_ORIGINS", "").strip()
if _cors_raw == "*":
    _cors_origins = ["*"]
    _cors_credentials = False
    logger.warning("CORS wildcard enabled (FLOOD_CORS_ORIGINS='*') â€“ credentials disabled")
elif _cors_raw:
    _cors_origins = [o.strip() for o in _cors_raw.split(",") if o.strip()]
    _cors_credentials = True
else:
    _cors_origins = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ]
    _cors_credentials = True

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=_cors_credentials,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key", "X-Request-ID"],
)

# Middleware order: last added runs outermost â†’ RequestID wraps Auth wraps CORS.
app.add_middleware(AuthRateLimitMiddleware, config=get_auth_config())
app.add_middleware(RequestIDMiddleware)

# â”€â”€â”€ Structured error envelope (T-01 / AC-04) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
app.add_exception_handler(APIError, api_error_handler)
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)

app.state.scheduler_leader = False

# â”€â”€â”€ Legacy deprecation headers (T-01): sunset unversioned paths â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
_LEGACY_PREFIXES = (
    "/predict", "/train", "/hotspots", "/wards",
    "/data", "/nowcast", "/email", "/health",
)


@app.middleware("http")
async def _legacy_sunset_headers(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path
    if not path.startswith("/v1") and path.startswith(_LEGACY_PREFIXES):
        response.headers["Deprecation"] = "true"
        response.headers["Sunset"] = "Wed, 30 Sep 2026 00:00:00 GMT"
        response.headers["Link"] = f'</v1{path}>; rel="successor-version"'
    return response


# â”€â”€â”€ API router (mounted at /v1 canonically + legacy for migration) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
router = APIRouter()


# â”€â”€â”€ Health â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
@router.get("/health", response_model=HealthResponse, tags=["System"])
async def health_check():
    """System health and model status."""
    status = await model_trainer.get_status()
    return HealthResponse(
        status="healthy",
        model_trained=status["trained"],
        model_accuracy=status.get("accuracy"),
        last_trained=status.get("last_trained"),
        hotspots_mapped=status.get("hotspots_mapped", 0),
        version=APP_VERSION,
    )


# â”€â”€â”€ Training â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
@router.post("/train", response_model=TrainingStatusResponse, tags=["Training"])
async def trigger_training(
    request: TrainingRequest,
    background_tasks: BackgroundTasks,
):
    """
    Trigger model training for a specific location.
    Pulls historical rainfall, DEM, LULC, soil, and drainage data,
    then trains a Random Forest + gradient-boosted ensemble.
    """
    background_tasks.add_task(
        model_trainer.train_for_location,
        lat=request.latitude,
        lon=request.longitude,
        radius_km=request.radius_km,
        years_back=request.years_back,
    )
    return TrainingStatusResponse(
        status="queued",
        message=f"Training queued for ({request.latitude}, {request.longitude}) "
                f"radius={request.radius_km}km, history={request.years_back}y",
    )


@router.get("/train/status", response_model=TrainingStatusResponse, tags=["Training"])
async def training_status():
    """Get current training job status and metrics."""
    status = await model_trainer.get_status()
    return TrainingStatusResponse(**status)


# â”€â”€â”€ Prediction â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
@router.post("/predict", response_model=PredictionResponse, tags=["Prediction"])
async def predict_flood(request: PredictionRequest):
    """
    Predict flood probability for a single location using all hydro factors:
    rainfall, elevation, slope, soil moisture, drainage capacity,
    LULC, impervious ratio, proximity to water bodies, and antecedent
    precipitation index.
    """
    if not await model_trainer.is_trained():
        raise APIError(503, "model_unavailable", "Model not yet trained. POST /v1/train first.")
    result = await flood_predictor.predict(request)
    return result


@router.post("/predict/bulk", response_model=BulkPredictionResponse, tags=["Prediction"])
async def predict_bulk(request: BulkPredictionRequest):
    """
    Batch-predict flood probability for multiple locations (up to 500).
    Ideal for grid-based micro-hotspot scanning of a city.
    """
    if not await model_trainer.is_trained():
        raise APIError(503, "model_unavailable", "Model not yet trained.")
    results = await flood_predictor.predict_bulk(request.locations)
    return BulkPredictionResponse(predictions=results, total=len(results))


# â”€â”€â”€ Micro-Hotspots â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
@router.get("/hotspots", response_model=MicroHotspotResponse, tags=["Analysis"])
async def get_micro_hotspots(
    lat: float = Query(..., description="Centre latitude"),
    lon: float = Query(..., description="Centre longitude"),
    radius_km: float = Query(10.0, description="Search radius in km"),
    grid_size_km: float = Query(1.0, description="Grid cell size (0.25â€“2 km)"),
    min_risk: float = Query(0.5, description="Minimum risk threshold (0â€“1)"),
):
    """
    Scan the area and return all micro-hotspot grid cells above the risk threshold.
    Supports 1Ã—1 km grids (default) down to 250m for high-resolution mapping.
    """
    if not await model_trainer.is_trained():
        raise APIError(503, "model_unavailable", "Model not yet trained.")
    hotspots = await flood_predictor.scan_hotspots(
        lat=lat,
        lon=lon,
        radius_km=radius_km,
        grid_size_km=grid_size_km,
        min_risk=min_risk,
    )
    return MicroHotspotResponse(
        centre_lat=lat,
        centre_lon=lon,
        radius_km=radius_km,
        grid_size_km=grid_size_km,
        total_cells_scanned=hotspots["total_cells"],
        hotspots_identified=hotspots["hotspot_count"],
        hotspots=hotspots["hotspots"],
    )


# â”€â”€â”€ Ward Readiness â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
@router.get("/wards/readiness", response_model=list[WardReadinessResponse], tags=["Analysis"])
async def ward_readiness(
    lat: float = Query(..., description="City centre latitude"),
    lon: float = Query(..., description="City centre longitude"),
    radius_km: float = Query(15.0, description="City radius km"),
):
    """
    Generate Pre-Monsoon Readiness Scores for all wards in the area.
    Returns A/B/C/D ranking based on predicted inundation depth,
    drainage health, and critical infrastructure exposure.
    """
    if not await model_trainer.is_trained():
        raise APIError(503, "model_unavailable", "Model not yet trained.")
    wards = await flood_predictor.compute_ward_readiness(lat, lon, radius_km)
    return wards


# â”€â”€â”€ Historical Data â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
@router.post("/data/ingest", tags=["Data"])
async def ingest_location_data(
    query: LocationQuery,
    background_tasks: BackgroundTasks,
):
    """
    Trigger historical data ingestion for a location (rainfall, DEM, LULC, soil).
    Runs in the background; check /train/status for completion.
    """
    background_tasks.add_task(
        data_collector.ingest_historical_data,
        lat=query.latitude,
        lon=query.longitude,
        radius_km=query.radius_km,
        years_back=query.years_back,
    )
    return {"status": "ingestion_queued", "location": {"lat": query.latitude, "lon": query.longitude}}


@router.get("/data/summary", tags=["Data"])
async def data_summary(
    lat: float = Query(...),
    lon: float = Query(...),
    radius_km: float = Query(10.0),
):
    """Return data availability summary for a location."""
    summary = await data_collector.get_data_summary(lat, lon, radius_km)
    return summary


# â”€â”€â”€ Nowcasting â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
@router.get("/nowcast", tags=["Prediction"])
async def nowcast(
    lat: float = Query(..., description="Latitude"),
    lon: float = Query(..., description="Longitude"),
    horizon_minutes: int = Query(45, description="Forecast horizon (30â€“120 min)"),
):
    """
    Real-time flood nowcasting for 30â€“120 minute horizon.
    Combines latest rainfall radar data with the ML model for rapid predictions.
    """
    if not await model_trainer.is_trained():
        raise APIError(503, "model_unavailable", "Model not yet trained.")
    return await flood_predictor.nowcast(lat, lon, horizon_minutes)


# â”€â”€â”€ Email Alerts â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
@router.get("/email/config", response_model=EmailConfigResponse, tags=["Email"])
async def email_config():
    """Check email notification configuration status."""
    return EmailConfigResponse(
        configured=is_email_configured(),
        smtp_host=SMTP_HOST if is_email_configured() else None,
        from_address=SMTP_FROM if is_email_configured() else None,
        default_recipients=ALERT_RECIPIENTS,
    )


@router.post("/email/ward-alert", response_model=EmailAlertResponse, tags=["Email"])
async def send_ward_email_alert(
    request: EmailAlertRequest,
    lat: float = Query(..., description="City centre latitude"),
    lon: float = Query(..., description="City centre longitude"),
    radius_km: float = Query(15.0, description="City radius km"),
):
    """
    Compute ward readiness and email results to the specified recipients.
    Sends alerts only if critical/high-risk wards are found (or recipients are explicitly provided).
    """
    if not await model_trainer.is_trained():
        raise APIError(503, "model_unavailable", "Model not yet trained.")

    wards = await flood_predictor.compute_ward_readiness(lat, lon, radius_km)
    ward_dicts = [w.model_dump() for w in wards]
    result = send_ward_alert(
        wards=ward_dicts,
        location=request.location,
        recipients=request.recipients,
    )
    return EmailAlertResponse(**result)


@router.post("/email/hotspot-alert", response_model=EmailAlertResponse, tags=["Email"])
async def send_hotspot_email_alert(
    request: EmailAlertRequest,
    lat: float = Query(..., description="Centre latitude"),
    lon: float = Query(..., description="Centre longitude"),
    radius_km: float = Query(10.0, description="Search radius km"),
    grid_size_km: float = Query(1.0, description="Grid cell size km"),
    min_risk: float = Query(0.5, description="Minimum risk threshold"),
):
    """
    Scan for micro-hotspots and email critical results to recipients.
    """
    if not await model_trainer.is_trained():
        raise APIError(503, "model_unavailable", "Model not yet trained.")

    hotspots = await flood_predictor.scan_hotspots(
        lat=lat, lon=lon, radius_km=radius_km,
        grid_size_km=grid_size_km, min_risk=min_risk,
    )
    hotspot_dicts = [h.model_dump() for h in hotspots["hotspots"]]
    result = send_hotspot_alert(
        hotspots=hotspot_dicts,
        total_scanned=hotspots["total_cells"],
        location=request.location,
        recipients=request.recipients,
    )
    return EmailAlertResponse(**result)


@router.post("/email/nowcast-alert", response_model=EmailAlertResponse, tags=["Email"])
async def send_nowcast_email_alert(
    request: EmailAlertRequest,
    lat: float = Query(..., description="Latitude"),
    lon: float = Query(..., description="Longitude"),
    horizon_minutes: int = Query(45, description="Forecast horizon (30â€“120 min)"),
):
    """
    Run nowcast and email the result if flood probability exceeds alert threshold.
    """
    if not await model_trainer.is_trained():
        raise APIError(503, "model_unavailable", "Model not yet trained.")

    nowcast_result = await flood_predictor.nowcast(lat, lon, horizon_minutes)
    result = send_nowcast_alert(
        nowcast=nowcast_result,
        location=request.location,
        recipients=request.recipients,
    )
    return EmailAlertResponse(**result)


# ─── Readiness probe (T-31) ───────────────────────────────────────────────────
@app.get("/ready", tags=["System"])
async def readiness():
    """Deep readiness probe: DB connectivity, model artefact integrity,
    scheduler leadership, auth mode. 200 when ready, 503 otherwise."""
    checks: dict = {}
    ok = True

    try:
        async with get_session() as session:
            await session.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:
        checks["database"] = f"error: {exc.__class__.__name__}"
        ok = False

    model = get_model()
    if model.is_trained:
        checks["model"] = "trained"
        verified = model.verify_artefact()
        checks["model_artefact"] = "verified" if verified else "unverified"
        if not verified:
            ok = False
    else:
        checks["model"] = "not_trained"
        checks["model_artefact"] = "missing"
        ok = False

    checks["scheduler"] = (
        "leader" if getattr(app.state, "scheduler_leader", False) else "standby"
    )
    checks["auth"] = "enabled" if get_auth_config().enabled else "disabled_dev_mode"

    body = ReadyResponse(
        status="ready" if ok else "not_ready", version=APP_VERSION, checks=checks
    )
    return JSONResponse(status_code=200 if ok else 503, content=body.model_dump())


# ─── Enriched single-point prediction (T-02, contract docs/06 §3.9) ───────────
def _severity_band(prob: float) -> str:
    if prob >= 0.85:
        return "S3_CRITICAL"
    if prob >= 0.65:
        return "S2_HIGH"
    if prob >= 0.40:
        return "S1_MEDIUM"
    return "S0_LOW"


@app.get("/v1/predict", response_model=EnrichedPredictionResponse, tags=["Prediction"])
async def predict_enriched(
    lat: float = Query(..., ge=-90, le=90, description="Decimal degrees latitude"),
    lon: float = Query(..., ge=-180, le=180, description="Decimal degrees longitude"),
    enrich: bool = Query(True, description="Fetch real covariates (False = schema defaults)"),
    month: Optional[int] = Query(None, ge=1, le=12, description="Override month (scenario runs)"),
):
    """Single-point prediction with REAL enriched features and per-field provenance."""
    if not await model_trainer.is_trained():
        raise APIError(503, "model_unavailable", "Model not yet trained. POST /v1/train first.")

    if enrich:
        result = await get_enrichment_service().enrich_point(lat, lon, month=month)
        req = result.to_prediction_request()
        provenance = {
            k: FieldProvenanceModel(
                source=v.source,
                fetched_at=v.fetched_at,
                cached=v.cached,
                fallback=v.fallback,
                spatial_uniform=v.spatial_uniform,
            )
            for k, v in result.provenance.items()
        }
        enriched_fields = result.enriched_fields
        missing = result.missing_covariates
        h3_index = result.h3_index
    else:
        req = PredictionRequest(
            latitude=lat, longitude=lon, **({"month": month} if month else {})
        )
        provenance = {}
        enriched_fields = []
        missing = [
            f
            for f in PredictionRequest.model_fields
            if f not in ("latitude", "longitude", "ward_id", "month", "hour_of_day")
        ]
        h3_index = h3_index_for(lat, lon)

    pred = await flood_predictor.predict(req)
    drivers = sorted(
        (
            DriverContribution(factor=k, contribution=float(v))
            for k, v in pred.contributing_factors.items()
        ),
        key=lambda d: -d.contribution,
    )[:8]
    return EnrichedPredictionResponse(
        h3_index=h3_index,
        h3_resolution=H3_RESOLUTION,
        latitude=lat,
        longitude=lon,
        flood_probability=pred.flood_probability,
        flood_risk_level=pred.flood_risk_level,
        severity_band=_severity_band(pred.flood_probability),
        estimated_inundation_depth_m=pred.estimated_inundation_depth_m,
        confidence=pred.confidence,
        drivers=drivers,
        recommendation=pred.recommendation,
        instruction=pred.recommendation,
        enriched_fields=enriched_fields,
        missing_covariates=missing,
        provenance=provenance,
        timestamp=pred.timestamp,
    )


# ─── Router mounting: canonical /v1 + legacy sunset (T-01) ────────────────────
app.include_router(router, prefix="/v1")
app.include_router(router, include_in_schema=False)  # legacy paths, sunset T-18

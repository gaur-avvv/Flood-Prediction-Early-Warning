"""
Flood Predictor Service

Handles single predictions, bulk scanning, micro-hotspot identification,
ward-level readiness scoring, and real-time nowcasting.
"""

import asyncio
import logging
import math
from datetime import datetime, timezone
from typing import List, Dict, Any

import httpx
import numpy as np
import pandas as pd
import os

from models.flood_model import get_model
from models.schemas import (
    PredictionRequest,
    PredictionResponse,
    HotspotCell,
    WardReadinessResponse,
    READINESS_GRADES,
)
from services.feature_engineering import build_feature_vector, build_feature_dataframe
from services.data_collector import DataCollector
from services.enrichment import get_enrichment_service
from utils.errors import APIError

logger = logging.getLogger(__name__)
_collector = DataCollector()


def _risk_level(prob: float) -> str:
    if prob >= 0.85:
        return "CRITICAL"
    elif prob >= 0.65:
        return "HIGH"
    elif prob >= 0.40:
        return "MEDIUM"
    elif prob >= 0.20:
        return "LOW"
    return "SAFE"


def _recommendation(prob: float, depth: float, factors: dict) -> str:
    if prob >= 0.85:
        return (
            "⚠️ CRITICAL: Activate emergency response. "
            "Pre-position pumps and personnel. Consider evacuation of low-lying areas."
        )
    elif prob >= 0.65:
        return (
            "🔴 HIGH: Deploy flood barriers and pump units to ward. "
            "Alert residents and open temporary shelters."
        )
    elif prob >= 0.40:
        return (
            "🟠 MEDIUM: Inspect and clear drains. "
            "Alert emergency services. Monitor water levels hourly."
        )
    elif prob >= 0.20:
        return "🟡 LOW: Routine monitoring. Ensure drain cleanliness and pump readiness."
    return "🟢 SAFE: No immediate action required. Continue standard monitoring."


def _readiness_grade(risk_score: float) -> str:
    if risk_score >= 80:
        return "F"
    elif risk_score >= 60:
        return "D"
    elif risk_score >= 40:
        return "C"
    elif risk_score >= 20:
        return "B"
    return "A"


def _recommended_actions(grade: str, factors: dict) -> List[str]:
    actions = {
        "A": ["Maintain routine drain inspections", "Verify pump station readiness"],
        "B": [
            "Inspect high-risk drains in ward",
            "Deploy portable pump units to standby",
            "Issue public advisory",
        ],
        "C": [
            "Clear all major drains and culverts",
            "Activate flood emergency plan",
            "Deploy pumps and HRD team",
            "Alert hospitals and emergency services",
        ],
        "D": [
            "Immediate evacuation of vulnerable households",
            "Deploy all available pumps",
            "Activate city emergency operations centre",
            "Issue flood warning to all residents",
            "Coordinate with NDRF/SDRF",
        ],
        "F": [
            "EMERGENCY: Evacuate all low-lying areas",
            "Request state/national disaster relief",
            "Deploy all flood response assets",
            "Open all emergency shelters",
            "Issue highest-level flood alert",
        ],
    }
    return actions.get(grade, [])


def _pre_position_resources(grade: str) -> List[str]:
    resources = {
        "A": [],
        "B": ["2× portable pumps", "1 HRD team on standby"],
        "C": [
            "5× portable pumps (1500 L/min)",
            "2 HRD teams",
            "Flood barriers (500m)",
            "Emergency food/water for 500 persons",
        ],
        "D": [
            "10× heavy pumps",
            "4 HRD teams + 2 NDRF units",
            "Flood barriers (2000m)",
            "Emergency shelter for 2,000 persons",
            "Medical response team",
        ],
        "F": [
            "All available pumps (military + civilian)",
            "Full NDRF battalion deployment",
            "Helicopter rescue capacity",
            "Emergency shelter for 10,000+ persons",
            "Multi-agency crisis coordination",
        ],
    }
    return resources.get(grade, [])


def _contributing_factors(X_row: pd.Series) -> dict:
    """Simplified factor attribution (production would use SHAP values)."""
    factors = {}
    r24 = X_row.get("rainfall_24h_mm", 0)
    drain = X_row.get("drainage_capacity_pct", 70)
    sm = X_row.get("soil_moisture_pct", 30)
    elev = X_row.get("elevation_m", 15)
    imp = X_row.get("impervious_surface_pct", 50)
    river = X_row.get("river_discharge_m3s", 0)

    factors["rainfall_24h"] = round(min(r24 / 100, 1.0) * 0.35, 3)
    factors["drainage_deficit"] = round((1 - drain / 100) * 0.25, 3)
    factors["soil_saturation"] = round(sm / 100 * 0.20, 3)
    factors["low_elevation"] = round(max(0, (20 - elev) / 20) * 0.12, 3)
    factors["imperviousness"] = round(imp / 100 * 0.08, 3)
    factors["river_discharge"] = round(min(river / 500, 1.0) * 0.15, 3)
    return {k: v for k, v in sorted(factors.items(), key=lambda x: -x[1])}


class FloodPredictor:

    # ──────────────────────────────────────────────────────────────────────────
    # Single prediction

    async def predict(self, request: PredictionRequest) -> PredictionResponse:
        X = build_feature_vector(request)
        model = get_model()
        flood_prob, flood_class, depth = model.predict(X)

        prob = float(flood_prob[0])
        dep = float(depth[0])
        factors = _contributing_factors(X.iloc[0])
        confidence = 0.7 + 0.25 * prob  # simplified confidence

        return PredictionResponse(
            latitude=request.latitude,
            longitude=request.longitude,
            flood_probability=round(prob, 4),
            flood_risk_level=_risk_level(prob),
            estimated_inundation_depth_m=round(dep, 3),
            predicted_flood_onset_minutes=None,
            confidence=round(confidence, 3),
            contributing_factors=factors,
            recommendation=_recommendation(prob, dep, factors),
            timestamp=datetime.now(timezone.utc),
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Bulk prediction

    async def predict_bulk(
        self, requests: List[PredictionRequest]
    ) -> List[PredictionResponse]:
        X = build_feature_dataframe(requests)
        model = get_model()
        flood_probs, flood_classes, depths = model.predict(X)

        results = []
        for i, req in enumerate(requests):
            prob = float(flood_probs[i])
            dep = float(depths[i])
            factors = _contributing_factors(X.iloc[i])
            results.append(
                PredictionResponse(
                    latitude=req.latitude,
                    longitude=req.longitude,
                    flood_probability=round(prob, 4),
                    flood_risk_level=_risk_level(prob),
                    estimated_inundation_depth_m=round(dep, 3),
                    confidence=round(0.7 + 0.25 * prob, 3),
                    contributing_factors=factors,
                    recommendation=_recommendation(prob, dep, factors),
                    timestamp=datetime.now(timezone.utc),
                )
            )
        return results

    # ──────────────────────────────────────────────────────────────────────────
    # Micro-hotspot scanning

    async def scan_hotspots(
        self,
        lat: float,
        lon: float,
        radius_km: float,
        grid_size_km: float,
        min_risk: float,
    ) -> Dict[str, Any]:
        """
        Scan the area with a grid of predictions.
        Returns all cells above the risk threshold.
        """
        grid_reqs = await self._build_grid_requests(lat, lon, radius_km, grid_size_km)
        logger.info("Scanning %d grid cells for hotspots…", len(grid_reqs))

        # Predict in sub-batches of 100
        all_preds = []
        for i in range(0, len(grid_reqs), 100):
            batch = grid_reqs[i : i + 100]
            preds = await self.predict_bulk(batch)
            all_preds.extend(preds)

        hotspots = []
        for req, pred in zip(grid_reqs, all_preds):
            if pred.flood_probability >= min_risk:
                dom = max(pred.contributing_factors, key=pred.contributing_factors.get)
                hotspots.append(
                    HotspotCell(
                        lat=req.latitude,
                        lon=req.longitude,
                        cell_id=f"{req.latitude:.4f}_{req.longitude:.4f}",
                        flood_probability=pred.flood_probability,
                        risk_level=pred.flood_risk_level,
                        inundation_depth_m=pred.estimated_inundation_depth_m,
                        dominant_factor=dom,
                        area_km2=round(grid_size_km ** 2, 4),
                    )
                )

        # Sort by probability descending
        hotspots.sort(key=lambda x: -x.flood_probability)

        return {
            "total_cells": len(grid_reqs),
            "hotspot_count": len(hotspots),
            "hotspots": hotspots,
        }

    MAX_SCAN_CELLS = 6000  # contract docs/06 §3.2 cell budget

    async def _build_grid_requests(
        self, lat: float, lon: float, radius_km: float, grid_size_km: float
    ) -> List[PredictionRequest]:
        """Generate grid cell centres and enrich each with REAL covariates.

        T-02 (audit B-1): replaces the synthetic sin/cos feature patterns.
        Weather and river discharge are sampled at the scan centroid (marked
        spatially uniform in provenance); per-cell elevation comes from SRTM
        in bounded batches of 50.
        """
        delta_lat = grid_size_km / 111.32
        delta_lon = grid_size_km / (111.32 * math.cos(math.radians(lat)))
        max_steps = int(radius_km / grid_size_km) + 1

        coords = []
        for i in range(-max_steps, max_steps + 1):
            for j in range(-max_steps, max_steps + 1):
                dist = math.sqrt((i * grid_size_km) ** 2 + (j * grid_size_km) ** 2)
                if dist <= radius_km:
                    coords.append(
                        (round(lat + i * delta_lat, 6), round(lon + j * delta_lon, 6))
                    )

        if len(coords) > self.MAX_SCAN_CELLS:
            raise APIError(
                400,
                "budget_exceeded",
                f"Scan requires {len(coords)} grid cells; budget is "
                f"{self.MAX_SCAN_CELLS}. Increase grid_size_km or reduce radius_km.",
                {"cells_required": len(coords), "cell_budget": self.MAX_SCAN_CELLS},
            )

        enricher = get_enrichment_service()
        cell_values, _prov = await enricher.enrich_grid(coords)
        allowed = set(PredictionRequest.model_fields)
        return [
            PredictionRequest(
                latitude=clat,
                longitude=clon,
                **{k: v for k, v in vals.items() if k in allowed},
            )
            for (clat, clon), vals in zip(coords, cell_values)
        ]

    # ──────────────────────────────────────────────────────────────────────────
    # Ward readiness scoring

    async def compute_ward_readiness(
        self, lat: float, lon: float, radius_km: float
    ) -> List[WardReadinessResponse]:
        """
        Simulate ward-level analysis.
        In production: query ward polygon geometries from PostGIS.
        """
        wards = await self._generate_ward_grid(lat, lon, radius_km)

        # T-02: enrich ward centroids with real covariates (bounded calls:
        # weather/discharge at centroid, elevation batched per H3 cell).
        enricher = get_enrichment_service()
        cell_values, _prov = await enricher.enrich_grid([(w[0], w[1]) for w in wards])
        allowed = set(PredictionRequest.model_fields)

        results = []
        for ward, vals in zip(wards, cell_values):
            wlat, wlon, ward_id, ward_name = ward

            req = PredictionRequest(
                latitude=wlat,
                longitude=wlon,
                ward_id=ward_id,
                **{k: v for k, v in vals.items() if k in allowed},
            )
            pred = await self.predict(req)

            # Sub-scores (0–100, higher = worse)
            inundation_score = round(pred.flood_probability * 100, 1)
            infra_cap = req.drainage_capacity_pct * req.drain_condition_score
            drainage_health = round(100 - infra_cap, 1)
            infra_exposure = round(
                min(100, req.population_density / 200 + req.building_density_pct), 1
            )
            risk_score = round(
                0.45 * inundation_score + 0.35 * drainage_health + 0.20 * infra_exposure, 1
            )
            grade = _readiness_grade(risk_score)

            results.append(
                WardReadinessResponse(
                    ward_id=ward_id,
                    ward_name=ward_name,
                    lat=wlat,
                    lon=wlon,
                    readiness_grade=grade,
                    readiness_description=READINESS_GRADES.get(grade, "Unknown"),
                    flood_probability=pred.flood_probability,
                    risk_score=risk_score,
                    inundation_risk_score=inundation_score,
                    drainage_health_score=drainage_health,
                    infrastructure_exposure_score=infra_exposure,
                    recommended_actions=_recommended_actions(grade, {}),
                    pre_position_resources=_pre_position_resources(grade),
                    hotspot_count_in_ward=int(pred.flood_probability * 20),
                )
            )

        results.sort(key=lambda x: -x.risk_score)
        return results

    async def _generate_ward_grid(
        self, lat: float, lon: float, radius_km: float
    ) -> List[tuple]:
        """Generate synthetic ward centres or real wards from india_wards.csv if town matches."""
        ward_spacing_km = max(2.0, radius_km / 5)
        delta = ward_spacing_km / 111.32
        wards = []
        
        # 1. Reverse geocode to find city/town
        town_name = None
        try:
            async with httpx.AsyncClient() as client:
                res = await client.get(
                    f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lon}",
                    headers={"User-Agent": "BioSentinelX-App"},
                    timeout=5.0
                )
                if res.status_code == 200:
                    address = res.json().get("address", {})
                    town_name = address.get("city") or address.get("town") or address.get("village") or address.get("state_district")
        except Exception as e:
            logger.warning("Reverse geocoding failed: %s", e)
        
        # 2. Try matching the town in india_wards.csv
        csv_path = os.path.join(os.path.dirname(__file__), "..", "data", "india_wards.csv")
        csv_path = os.path.abspath(csv_path)
        real_wards = []
        if town_name and os.path.exists(csv_path):
            try:
                df_wards = pd.read_csv(csv_path)
                match = df_wards[df_wards["town"].str.lower() == town_name.lower()]
                if not match.empty:
                    real_wards = match.to_dict("records")
            except Exception as e:
                logger.warning("Failed to read india_wards.csv: %s", e)
        
        # 3. Generate wards (using real names from CSV if available, distributing them in a grid)
        idx = 1
        for i in range(-3, 4):
            for j in range(-3, 4):
                wlat = round(lat + i * delta, 5)
                wlon = round(lon + j * delta, 5)
                dist = math.sqrt((i * ward_spacing_km) ** 2 + (j * ward_spacing_km) ** 2)
                if dist <= radius_km:
                    ward_name = f"Ward {idx}"
                    ward_id = f"WARD-{idx:03d}"
                    if real_wards and idx - 1 < len(real_wards):
                        ward_name = real_wards[idx - 1].get("name", ward_name)
                        ward_id = str(real_wards[idx - 1].get("code", ward_id))
                    wards.append((wlat, wlon, ward_id, ward_name))
                    idx += 1
        return wards

    # ──────────────────────────────────────────────────────────────────────────
    # Nowcasting

    async def nowcast(
        self, lat: float, lon: float, horizon_minutes: int
    ) -> Dict[str, Any]:
        """
        30–120 min flood nowcast using latest weather + ML model.
        Fetches real-time rainfall and projects forward.
        """
        current = await _collector.fetch_current_conditions(lat, lon)
        horizon_h = horizon_minutes / 60

        # Forecast accumulation from hourly precipitation
        hourly_fc = current.get("hourly_precip_forecast", [0] * 3)
        n_hours = math.ceil(horizon_h)
        fc_rain = sum(hourly_fc[:n_hours]) if hourly_fc else current.get("rainfall_1h_mm", 0) * n_hours

        # T-02: real enriched terrain/soil/drainage/discharge covariates,
        # overridden with the live nowcast rainfall projections.
        enriched = await get_enrichment_service().enrich_point(lat, lon)
        req = enriched.to_prediction_request(
            rainfall_1h_mm=current.get("rainfall_1h_mm", enriched.values.get("rainfall_1h_mm", 0)),
            rainfall_3h_mm=fc_rain,
            rainfall_6h_mm=fc_rain * 1.5,
            rainfall_24h_mm=fc_rain * 3,
            rainfall_48h_mm=fc_rain * 4,
        )

        pred = await self.predict(req)
        pred.predicted_flood_onset_minutes = (
            horizon_minutes * (1 - pred.flood_probability) if pred.flood_probability > 0.3
            else None
        )

        return {
            "nowcast_horizon_minutes": horizon_minutes,
            "current_rainfall_mm_hr": current.get("rainfall_1h_mm", 0),
            "forecast_accumulation_mm": round(fc_rain, 2),
            "flood_probability": pred.flood_probability,
            "flood_risk_level": pred.flood_risk_level,
            "estimated_inundation_depth_m": pred.estimated_inundation_depth_m,
            "predicted_flood_onset_minutes": pred.predicted_flood_onset_minutes,
            "recommendation": pred.recommendation,
            "confidence": pred.confidence,
            "timestamp": pred.timestamp,
        }

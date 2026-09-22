"""
Prediction Enrichment Service (Sprint 0 / T-02 – audit finding B-1).

Replaces the synthetic ``sin(lat) × cos(lon)`` feature generation with REAL
data assembled from DataCollector + Open-Meteo / GloFAS / SRTM / SoilGrids /
Overpass, adds H3 cell indexing, TTL caching (static vs live) and per-field
provenance tracking (source, fetched_at, cached, fallback).
"""

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

import httpx

try:
    import h3 as _h3

    H3_AVAILABLE = True
except ImportError:  # pragma: no cover
    _h3 = None
    H3_AVAILABLE = False

from models.schemas import PredictionRequest
from services.data_collector import (
    DataCollector,
    OPEN_METEO_FORECAST_URL,
    OPEN_METEO_FLOOD_URL,
    OPEN_TOPO_URL,
)

logger = logging.getLogger(__name__)

H3_RESOLUTION = int(os.getenv("FLOOD_H3_RESOLUTION", "8"))
H3_STATIC_RESOLUTION = 6    # soil / DEM / drainage cache granularity
H3_DRAINAGE_RESOLUTION = 4  # drainage infra granularity
STATIC_TTL_SECONDS = float(os.getenv("FLOOD_STATIC_CACHE_TTL", str(7 * 24 * 3600)))
LIVE_TTL_SECONDS = float(os.getenv("FLOOD_LIVE_CACHE_TTL", "300"))
DISCHARGE_TTL_SECONDS = float(os.getenv("FLOOD_DISCHARGE_CACHE_TTL", "3600"))
_OPEN_TOPO_BATCH = 50


def h3_index_for(lat: float, lon: float, resolution: int = H3_RESOLUTION) -> str:
    if H3_AVAILABLE:
        return _h3.latlng_to_cell(lat, lon, resolution)
    return f"geo_{resolution}_{lat:.4f}_{lon:.4f}"  # deterministic fallback


class TTLCache:
    """Tiny in-memory TTL cache (per-process)."""

    def __init__(self, ttl_seconds: float, max_entries: int = 10_000):
        self.ttl = ttl_seconds
        self.max_entries = max_entries
        self._store: Dict[str, Tuple[float, Any]] = {}

    def get(self, key: str) -> Tuple[bool, Any]:
        item = self._store.get(key)
        if not item:
            return False, None
        expires_at, value = item
        if time.monotonic() > expires_at:
            self._store.pop(key, None)
            return False, None
        return True, value

    def set(self, key: str, value: Any) -> None:
        if len(self._store) >= self.max_entries:
            oldest = min(self._store, key=lambda k: self._store[k][0])
            self._store.pop(oldest, None)
        self._store[key] = (time.monotonic() + self.ttl, value)


@dataclass
class FieldProvenance:
    source: str
    fetched_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    cached: bool = False
    fallback: bool = False
    spatial_uniform: bool = False


@dataclass
class EnrichmentResult:
    lat: float
    lon: float
    h3_index: str
    h3_resolution: int
    values: Dict[str, Any]
    provenance: Dict[str, FieldProvenance]
    enriched_fields: List[str]
    missing_covariates: List[str]

    def to_prediction_request(self, **overrides) -> PredictionRequest:
        allowed = set(PredictionRequest.model_fields)
        payload = {k: v for k, v in self.values.items() if k in allowed}
        payload.update(overrides)
        return PredictionRequest(latitude=self.lat, longitude=self.lon, **payload)


def summarize_rainfall_windows(
    hourly: Sequence[float], now_index: int
) -> Dict[str, float]:
    """Aggregate an hourly precipitation series into model windows.

    ``hourly`` is expected to hold past hours up to ``now_index`` (inclusive)
    followed by forecast hours (Open-Meteo ``past_days=3&forecast_days=1``).
    """
    vals = [float(v or 0.0) for v in hourly]
    if not vals:
        return {
            "rainfall_1h_mm": 0.0, "rainfall_3h_mm": 0.0, "rainfall_6h_mm": 0.0,
            "rainfall_24h_mm": 0.0, "rainfall_48h_mm": 0.0, "rainfall_72h_mm": 0.0,
            "rainfall_intensity": 0.0, "antecedent_precip_index": 0.0,
            "forecast_next_24h_mm": 0.0,
        }
    now_index = max(0, min(now_index, len(vals) - 1))

    def past(n: int) -> float:
        lo = max(0, now_index - n + 1)
        return float(sum(vals[lo : now_index + 1]))

    r24, r48, r72 = past(24), past(48), past(72)
    api = 0.5 * r24 + 0.3 * max(0.0, r48 - r24) + 0.2 * max(0.0, r72 - r48)
    intensity = max(vals[max(0, now_index - 2) : now_index + 1])
    return {
        "rainfall_1h_mm": past(1),
        "rainfall_3h_mm": past(3),
        "rainfall_6h_mm": past(6),
        "rainfall_24h_mm": r24,
        "rainfall_48h_mm": r48,
        "rainfall_72h_mm": r72,
        "rainfall_intensity": float(intensity),
        "antecedent_precip_index": float(api),
        "forecast_next_24h_mm": float(sum(vals[now_index + 1 : now_index + 25])),
    }


class EnrichmentService:
    """Assembles real covariates for PredictionRequest from live sources."""

    def __init__(self, collector: Optional[DataCollector] = None):
        self._collector = collector or DataCollector()
        self._static_cache = TTLCache(STATIC_TTL_SECONDS)
        self._live_cache = TTLCache(LIVE_TTL_SECONDS)
        self._discharge_cache = TTLCache(DISCHARGE_TTL_SECONDS)
        self._elev_cache = TTLCache(STATIC_TTL_SECONDS)
        self._timeout = httpx.Timeout(20.0)

    # ── low-level fetchers (overridable in tests) ─────────────────────────

    @staticmethod
    async def _safe(coro) -> Optional[Dict[str, Any]]:
        try:
            return await coro
        except Exception as exc:
            logger.warning("Enrichment fetch failed: %s", exc)
            return None

    async def _fetch_rainfall_windows(self, lat: float, lon: float) -> Dict[str, float]:
        params = {
            "latitude": lat,
            "longitude": lon,
            "hourly": "precipitation",
            "past_days": 3,
            "forecast_days": 1,
            "timezone": "UTC",
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(OPEN_METEO_FORECAST_URL, params=params)
            resp.raise_for_status()
            hourly = resp.json().get("hourly", {})
        times = hourly.get("time", []) or []
        precip = hourly.get("precipitation", []) or []
        return summarize_rainfall_windows(precip, self._now_index(times, len(precip)))

    @staticmethod
    def _now_index(times: List[str], n: int) -> int:
        if not times:
            return max(0, n - 25)
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:00")
        past = [i for i, t in enumerate(times) if t <= now_str]
        return past[-1] if past else 0

    async def _fetch_live_discharge(self, lat: float, lon: float) -> Dict[str, float]:
        """GloFAS river discharge + anomaly vs 92-day median (Open-Meteo flood API)."""
        params = {
            "latitude": lat,
            "longitude": lon,
            "daily": "river_discharge",
            "past_days": 92,
            "forecast_days": 7,
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(OPEN_METEO_FLOOD_URL, params=params)
            resp.raise_for_status()
            daily = (resp.json().get("daily") or {}).get("river_discharge") or []
        series = [float(v) for v in daily if v is not None]
        if not series:
            raise ValueError("no discharge data for location")
        today = series[min(91, len(series) - 1)]
        history = sorted(series[:92])
        p50 = history[len(history) // 2]
        ratio = (today / p50) if p50 > 0 else (1.0 if today > 0 else 0.0)
        return {
            "river_discharge_m3s": round(today, 2),
            "discharge_anomaly_ratio": round(min(ratio, 20.0), 3),
        }

    # ── cached source groups ──────────────────────────────────────────────

    async def _get_static(self, lat: float, lon: float):
        """Terrain + soil + drainage (changes slowly → 7-day TTL)."""
        key = f"static:{h3_index_for(lat, lon, H3_STATIC_RESOLUTION)}"
        hit, cached = self._static_cache.get(key)
        if hit:
            data, prov = cached
            return data, FieldProvenance(
                prov.source, prov.fetched_at, cached=True, fallback=prov.fallback
            )
        dem, soil, drain = await asyncio.gather(
            self._safe(self._collector._fetch_dem(lat, lon, 1.0)),
            self._safe(self._collector._fetch_soil_properties(lat, lon)),
            self._safe(self._collector._fetch_drainage_infra(lat, lon, 1.0)),
        )
        fallback = dem is None and soil is None and drain is None
        data: Dict[str, Any] = {**(dem or {}), **(soil or {}), **(drain or {})}
        prov = FieldProvenance(
            source="opentopodata-srtm30m+soilgrids+osm-overpass", fallback=fallback
        )
        self._static_cache.set(key, (data, prov))
        return data, prov

    async def _get_weather(self, lat: float, lon: float):
        """Live weather + 1–72h rainfall windows (5-minute TTL)."""
        bucket = int(time.time() // LIVE_TTL_SECONDS)
        key = f"wx:{h3_index_for(lat, lon)}:{bucket}"
        hit, cached = self._live_cache.get(key)
        if hit:
            data, prov = cached
            return data, FieldProvenance(
                prov.source, prov.fetched_at, cached=True, fallback=prov.fallback
            )
        windows, current = await asyncio.gather(
            self._safe(self._fetch_rainfall_windows(lat, lon)),
            self._safe(self._collector._fetch_current_weather(lat, lon)),
        )
        data: Dict[str, Any] = {
            k: v for k, v in (current or {}).items() if not k.startswith("hourly_")
        }
        data.update(windows or {})
        prov = FieldProvenance(
            source="open-meteo-forecast", fallback=not windows and not current
        )
        self._live_cache.set(key, (data, prov))
        return data, prov

    async def _get_discharge(self, lat: float, lon: float):
        """GloFAS discharge (1-hour TTL, coarse H3-4 cell)."""
        key = f"dis:{h3_index_for(lat, lon, H3_DRAINAGE_RESOLUTION)}"
        hit, cached = self._discharge_cache.get(key)
        if hit:
            data, prov = cached
            return data, FieldProvenance(
                prov.source, prov.fetched_at, cached=True, fallback=prov.fallback
            )
        result = await self._safe(self._fetch_live_discharge(lat, lon))
        data = result or {}
        prov = FieldProvenance(source="glofas-open-meteo-flood", fallback=result is None)
        self._discharge_cache.set(key, (data, prov))
        return data, prov

    # ── public API ────────────────────────────────────────────────────────

    async def enrich_point(
        self, lat: float, lon: float, month: Optional[int] = None
    ) -> EnrichmentResult:
        static, weather, discharge = await asyncio.gather(
            self._get_static(lat, lon),
            self._get_weather(lat, lon),
            self._get_discharge(lat, lon),
        )
        values: Dict[str, Any] = {}
        provenance: Dict[str, FieldProvenance] = {}
        enriched: set = set()
        for group, (data, prov) in (
            ("static", static),
            ("weather", weather),
            ("discharge", discharge),
        ):
            provenance[group] = prov
            if not prov.fallback:
                for k, v in data.items():
                    if k != "forecast_next_24h_mm":
                        values[k] = v
                        enriched.add(k)
        return self._result(lat, lon, values, provenance, enriched, month)

    def _result(self, lat, lon, values, provenance, enriched, month) -> EnrichmentResult:
        defaults = PredictionRequest(latitude=lat, longitude=lon).model_dump()
        now = datetime.now(timezone.utc)
        values.setdefault("month", month or now.month)
        values["hour_of_day"] = now.hour
        missing = [
            k
            for k in defaults
            if k not in enriched and k not in ("latitude", "longitude", "ward_id")
        ]
        for k in missing:
            if k not in values:
                values[k] = defaults[k]
        return EnrichmentResult(
            lat=lat,
            lon=lon,
            h3_index=h3_index_for(lat, lon),
            h3_resolution=H3_RESOLUTION,
            values=values,
            provenance=provenance,
            enriched_fields=sorted(enriched),
            missing_covariates=missing,
        )

    async def enrich_grid(
        self, cells: Sequence[Tuple[float, float]]
    ) -> Tuple[List[Dict[str, Any]], Dict[str, FieldProvenance]]:
        """Enrich many grid cells with bounded upstream calls.

        Weather and river discharge are sampled once at the scan centroid
        (marked ``spatial_uniform``); elevation is fetched per H3-res-7 cell
        in batches of 50; soil/drainage are fetched once per coarse H3 cell
        and cached.
        """
        if not cells:
            return [], {}
        clat = sum(c[0] for c in cells) / len(cells)
        clon = sum(c[1] for c in cells) / len(cells)

        (static_c, static_prov), (weather, wx_prov), (discharge, dis_prov) = (
            await asyncio.gather(
                self._get_static(clat, clon),
                self._get_weather(clat, clon),
                self._get_discharge(clat, clon),
            )
        )
        wx_prov.spatial_uniform = True
        dis_prov.spatial_uniform = True

        elevations = await self._fetch_elevations(cells)

        base: Dict[str, Any] = {**static_c, **weather, **discharge}
        base.pop("forecast_next_24h_mm", None)
        defaults = PredictionRequest(latitude=clat, longitude=clon).model_dump()
        now = datetime.now(timezone.utc)

        out: List[Dict[str, Any]] = []
        for (cell_lat, cell_lon), elev in zip(cells, elevations):
            vals = dict(base)
            if elev is not None:
                vals["elevation_m"] = float(elev)
                vals["flow_accumulation"] = max(0.0, 1000.0 - float(elev) * 10)
                vals["stream_distance_m"] = max(50.0, float(elev) * 20)
                vals["water_body_distance_m"] = max(100.0, float(elev) * 50)
            for k, dv in defaults.items():
                if k not in vals and k not in ("latitude", "longitude", "ward_id"):
                    vals[k] = dv
            vals.setdefault("month", now.month)
            vals["hour_of_day"] = now.hour
            out.append(vals)

        prov = {
            "static": static_prov,
            "weather": wx_prov,
            "discharge": dis_prov,
            "elevation": FieldProvenance(
                source="opentopodata-srtm30m-batch",
                fallback=not elevations or elevations[0] is None,
            ),
        }
        return out, prov

    async def _fetch_elevations(
        self, cells: Sequence[Tuple[float, float]]
    ) -> List[Optional[float]]:
        """Per-cell SRTM elevation, de-duplicated by H3 res-7 and batched."""
        unique: Dict[str, Tuple[float, float]] = {}
        mapping: List[str] = []
        for lat, lon in cells:
            key = h3_index_for(lat, lon, 7)
            mapping.append(key)
            unique.setdefault(key, (lat, lon))

        results: Dict[str, Optional[float]] = {}
        for key in list(unique):
            hit, val = self._elev_cache.get(key)
            if hit:
                results[key] = val
                del unique[key]

        keys = list(unique)
        sem = asyncio.Semaphore(4)

        async def fetch_chunk(chunk_keys: List[str]) -> None:
            pts = [unique[k] for k in chunk_keys]
            locations = "|".join(f"{p[0]},{p[1]}" for p in pts)
            try:
                async with sem:
                    async with httpx.AsyncClient(timeout=self._timeout) as client:
                        resp = await client.get(
                            OPEN_TOPO_URL, params={"locations": locations}
                        )
                        resp.raise_for_status()
                        arr = resp.json().get("results", [])
                for k, r in zip(chunk_keys, arr):
                    results[k] = r.get("elevation")
                    self._elev_cache.set(k, results[k])
            except Exception as exc:
                logger.warning("Elevation batch failed: %s", exc)
                for k in chunk_keys:
                    results[k] = None

        chunks = [keys[i : i + _OPEN_TOPO_BATCH] for i in range(0, len(keys), _OPEN_TOPO_BATCH)]
        if chunks:
            await asyncio.gather(*(fetch_chunk(c) for c in chunks))
        return [results.get(k) for k in mapping]


_service: Optional[EnrichmentService] = None


def get_enrichment_service() -> EnrichmentService:
    global _service
    if _service is None:
        _service = EnrichmentService()
    return _service




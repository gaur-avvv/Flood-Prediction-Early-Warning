"""Unit tests for the enrichment service (T-02) – fully offline via stubs."""

import time

import pytest

from services.enrichment import (
    EnrichmentService,
    TTLCache,
    h3_index_for,
    summarize_rainfall_windows,
)


def test_ttl_cache_hit_and_expiry():
    c = TTLCache(ttl_seconds=0.05)
    c.set("a", 1)
    assert c.get("a") == (True, 1)
    time.sleep(0.06)
    assert c.get("a") == (False, None)


def test_rainfall_windows_aggregation():
    hourly = [1.0] * 72 + [0.5] * 24  # 72h past @1mm/h + 24h forecast @0.5mm/h
    r = summarize_rainfall_windows(hourly, now_index=71)
    assert r["rainfall_1h_mm"] == pytest.approx(1.0)
    assert r["rainfall_3h_mm"] == pytest.approx(3.0)
    assert r["rainfall_24h_mm"] == pytest.approx(24.0)
    assert r["rainfall_72h_mm"] == pytest.approx(72.0)
    assert r["forecast_next_24h_mm"] == pytest.approx(12.0)
    assert r["antecedent_precip_index"] > 0
    assert r["rainfall_intensity"] == pytest.approx(1.0)


def test_h3_index_deterministic():
    a = h3_index_for(19.076, 72.877)
    assert a == h3_index_for(19.076, 72.877)
    assert isinstance(a, str) and a


class _StubCollector:
    async def _fetch_dem(self, lat, lon, radius_km):
        return {
            "elevation_m": 12.0, "slope_degrees": 1.5, "curvature": 0.2,
            "flow_accumulation": 800.0, "stream_distance_m": 240.0,
            "water_body_distance_m": 600.0, "aspect_degrees": 180.0,
        }

    async def _fetch_soil_properties(self, lat, lon):
        return {"soil_type_code": 4, "clay_pct": 30.0}

    async def _fetch_drainage_infra(self, lat, lon, radius_km):
        return {
            "pump_stations_count": 3, "drainage_capacity_pct": 55.0,
            "drain_age_years": 25, "drain_condition_score": 0.7,
            "sewer_overflow_events_30d": 1,
        }

    async def _fetch_current_weather(self, lat, lon):
        return {
            "temperature_c": 29.0, "humidity_pct": 80.0, "wind_speed_ms": 4.0,
            "wind_direction_deg": 220.0, "pressure_hpa": 1005.0,
            "soil_moisture_pct": 55.0,
        }


class _StubService(EnrichmentService):
    async def _fetch_rainfall_windows(self, lat, lon):
        return summarize_rainfall_windows([2.0] * 72 + [1.0] * 24, 71)

    async def _fetch_live_discharge(self, lat, lon):
        return {"river_discharge_m3s": 120.0, "discharge_anomaly_ratio": 2.5}


async def test_enrich_point_real_values_and_provenance():
    svc = _StubService(collector=_StubCollector())
    result = await svc.enrich_point(19.076, 72.877)

    assert result.values["rainfall_24h_mm"] == pytest.approx(48.0)
    assert result.values["elevation_m"] == 12.0
    assert result.values["river_discharge_m3s"] == 120.0
    assert result.values["soil_type_code"] == 4
    assert "rainfall_24h_mm" in result.enriched_fields
    assert "elevation_m" in result.enriched_fields
    # fields with no real source (e.g. population density) are listed as missing
    assert "population_density" in result.missing_covariates
    assert set(result.provenance) == {"static", "weather", "discharge"}
    assert not any(p.fallback for p in result.provenance.values())

    req = result.to_prediction_request()
    assert req.latitude == 19.076
    assert req.elevation_m == 12.0
    assert req.rainfall_72h_mm == pytest.approx(144.0)


class _FailCollector:
    async def _fetch_dem(self, *a, **k):
        raise ConnectionError("offline")

    async def _fetch_soil_properties(self, *a, **k):
        raise ConnectionError("offline")

    async def _fetch_drainage_infra(self, *a, **k):
        raise ConnectionError("offline")

    async def _fetch_current_weather(self, *a, **k):
        raise ConnectionError("offline")


class _FailService(EnrichmentService):
    async def _fetch_rainfall_windows(self, lat, lon):
        raise ConnectionError("offline")

    async def _fetch_live_discharge(self, lat, lon):
        raise ConnectionError("offline")


async def test_enrich_point_fallback_when_all_sources_down():
    svc = _FailService(collector=_FailCollector())
    result = await svc.enrich_point(19.076, 72.877)
    assert all(p.fallback for p in result.provenance.values())
    assert "rainfall_24h_mm" in result.missing_covariates
    req = result.to_prediction_request()  # must still build with defaults
    assert req.rainfall_24h_mm == 0.0


async def test_enrich_grid_aligns_and_bounds():
    svc = _StubService(collector=_StubCollector())

    async def fake_elevations(cells):
        return [10.0 + i for i, _ in enumerate(cells)]

    svc._fetch_elevations = fake_elevations
    cells = [(19.07, 72.87), (19.08, 72.88), (19.09, 72.89)]
    values, prov = await svc.enrich_grid(cells)
    assert len(values) == 3
    assert [v["elevation_m"] for v in values] == [10.0, 11.0, 12.0]
    assert all(v["rainfall_24h_mm"] == pytest.approx(48.0) for v in values)
    assert prov["weather"].spatial_uniform is True
    assert "elevation" in prov

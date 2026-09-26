import pytest
import os
import pandas as pd
from services.predictor import (
    FloodPredictor,
    _risk_level,
    _readiness_grade,
    _contributing_factors,
)

def test_risk_level_and_readiness_grading():
    """Verify threshold mapping for operational risk levels and readiness grades."""
    assert _risk_level(0.90) == "CRITICAL"
    assert _risk_level(0.70) == "HIGH"
    assert _risk_level(0.45) == "MEDIUM"
    assert _risk_level(0.25) == "LOW"
    assert _risk_level(0.10) == "SAFE"

    assert _readiness_grade(85.0) == "F"
    assert _readiness_grade(65.0) == "D"
    assert _readiness_grade(45.0) == "C"
    assert _readiness_grade(25.0) == "B"
    assert _readiness_grade(10.0) == "A"

def test_contributing_factors_attribution():
    """Verify contributing factors incorporate rainfall, TWI, and drainage stress."""
    row = pd.Series({
        "rainfall_24h_mm": 150.0,
        "drainage_capacity_pct": 30.0,
        "soil_moisture_pct": 85.0,
        "elevation_m": 5.0,
        "impervious_surface_pct": 80.0,
        "topographic_wetness_index": 8.5,
        "drainage_stress": 2.2,
    })
    factors = _contributing_factors(row)
    assert "rainfall_24h" in factors
    assert "topographic_wetness" in factors
    assert "drainage_stress" in factors
    assert factors["rainfall_24h"] > 0

@pytest.mark.asyncio
async def test_real_wards_resolution():
    """Verify real municipal ward centroids resolve from india_wards.csv for Mumbai."""
    predictor = FloodPredictor()
    wards = await predictor._generate_ward_grid(lat=19.0760, lon=72.8777, radius_km=15.0)
    assert len(wards) > 0
    ward_codes = [w[2] for w in wards]
    # Check that MCGM ward codes appear
    assert any("MCGM" in code for code in ward_codes)

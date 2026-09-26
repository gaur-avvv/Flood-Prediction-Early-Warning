import numpy as np
import pandas as pd
from models.schemas import PredictionRequest
from services.feature_engineering import (
    build_feature_vector,
    _curve_number,
    _runoff_depth_mm,
    engineer_training_features,
)
from models.flood_model import FEATURE_COLUMNS

def test_curve_number_and_runoff_calculation():
    """Verify SCS-CN hydrologic runoff physics."""
    # Urban impervious should yield higher CN than forest
    cn_urban = _curve_number(lulc=1, soil=2)
    cn_forest = _curve_number(lulc=3, soil=2)
    assert cn_urban > cn_forest

    # Runoff must be 0 when rainfall is below initial abstraction
    runoff_dry = _runoff_depth_mm(rainfall_mm=2.0, cn=80)
    assert runoff_dry == 0.0

    # Runoff must be positive and less than total precipitation for heavy storm
    runoff_heavy = _runoff_depth_mm(rainfall_mm=100.0, cn=85)
    assert 0.0 < runoff_heavy < 100.0

def test_topographic_wetness_index_in_feature_vector():
    """Verify TWI formulation and presence in canonical feature columns."""
    req = PredictionRequest(
        latitude=19.0760,
        longitude=72.8777,
        rainfall_1h_mm=10.0,
        rainfall_24h_mm=80.0,
        elevation_m=12.0,
        slope_degrees=2.5,
        flow_accumulation=1500.0,
    )
    df = build_feature_vector(req)
    assert len(df.columns) == len(FEATURE_COLUMNS)
    assert "topographic_wetness_index" in df.columns
    assert "compound_hazard_index" in df.columns

    # TWI must be positive for low slopes with high contributing area
    twi_val = df["topographic_wetness_index"].iloc[0]
    assert twi_val > 0

def test_engineer_training_features():
    """Verify batch DataFrame transformation matches canonical schema."""
    df_raw = pd.DataFrame([{
        "rainfall_1h_mm": 15.0,
        "rainfall_3h_mm": 25.0,
        "rainfall_6h_mm": 40.0,
        "rainfall_24h_mm": 90.0,
        "rainfall_48h_mm": 120.0,
        "rainfall_72h_mm": 130.0,
        "rainfall_intensity": 15.0,
        "antecedent_precip_index": 50.0,
        "elevation_m": 10.0,
        "slope_degrees": 1.5,
        "aspect_degrees": 180.0,
        "curvature": 0.05,
        "flow_accumulation": 800.0,
        "stream_distance_m": 150.0,
        "water_body_distance_m": 300.0,
        "soil_type_code": 4,
        "soil_moisture_pct": 65.0,
        "lulc_code": 1,
        "impervious_surface_pct": 75.0,
        "ndvi": 0.25,
        "drainage_capacity_pct": 55.0,
        "drain_age_years": 20,
        "drain_condition_score": 0.7,
        "pump_stations_count": 2,
        "sewer_overflow_events_30d": 0,
        "temperature_c": 27.0,
        "humidity_pct": 80.0,
        "wind_speed_ms": 6.0,
        "wind_direction_deg": 220.0,
        "evapotranspiration_mm": 3.0,
        "pressure_hpa": 1008.0,
        "population_density": 10000.0,
        "building_density_pct": 55.0,
        "green_space_pct": 10.0,
        "previous_flood_events_5y": 2,
        "month": 7,
        "hour_of_day": 14,
    }])
    transformed = engineer_training_features(df_raw)
    assert list(transformed.columns) == FEATURE_COLUMNS
    assert not transformed.isna().any().any()

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, date
from services.data_collector import DataCollector

def test_flood_history_datetime_index_parsing():
    """Verify that pd.to_datetime on a list of dates produces date objects without .dt attribute error."""
    times = ["2026-01-01", "2026-01-02", "2026-01-03"]
    dates = pd.to_datetime(times).date if len(times) > 0 else []
    df = pd.DataFrame({
        "date": dates,
        "river_discharge_m3s": [12.5, 15.0, 20.3],
    })
    assert len(df) == 3
    assert isinstance(df["date"].iloc[0], date)
    assert df["river_discharge_m3s"].iloc[1] == 15.0

def test_synthetic_rainfall_generator():
    """Verify synthetic monsoon data generation has realistic properties."""
    collector = DataCollector()
    start = date(2025, 6, 1)
    end = date(2025, 9, 30)
    df = collector._synthetic_rainfall_df(lat=19.0760, lon=72.8777, start=start, end=end)
    assert not df.empty
    assert "rainfall_1h_mm" in df.columns
    assert "rainfall_24h_mm" in df.columns
    assert "antecedent_precip_index" in df.columns
    assert df["rainfall_24h_mm"].max() >= df["rainfall_1h_mm"].max()

def test_empirical_flood_overlay():
    """Verify empirical flood events correctly overlay onto observation timelines."""
    collector = DataCollector()
    # Create test observation DataFrame
    dates = pd.date_range("2005-07-25", "2005-07-28", freq="h")
    df = pd.DataFrame({
        "date_time": dates,
        "rainfall_1h_mm": [5.0] * len(dates),
        "rainfall_24h_mm": [50.0] * len(dates),
        "flood_occurred": [0] * len(dates),
        "inundation_depth_m": [0.0] * len(dates),
        "drainage_capacity_pct": [60.0] * len(dates),
        "drain_condition_score": [0.7] * len(dates),
        "lat": [19.0730] * len(dates),
        "lon": [72.8820] * len(dates),
    })
    df_overlaid = collector._overlay_empirical_flood_events(df, lat=19.0730, lon=72.8820)
    # 2005-07-26 should be marked as flood with recorded depth (2.8m from MCGM records)
    event_mask = pd.to_datetime(df_overlaid["date_time"]).dt.date == date(2005, 7, 26)
    assert df_overlaid.loc[event_mask, "flood_occurred"].sum() > 0
    assert df_overlaid.loc[event_mask, "inundation_depth_m"].max() >= 2.80

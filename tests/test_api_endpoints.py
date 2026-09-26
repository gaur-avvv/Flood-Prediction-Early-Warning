import pytest
from fastapi.testclient import TestClient
from main import app

@pytest.fixture(scope="module")
def client():
    return TestClient(app)

def test_health_endpoint(client):
    """Test /health system endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "model_trained" in data
    assert "version" in data

def test_predict_endpoint(client):
    """Test /predict single-point forecast endpoint."""
    response = client.post("/predict", json={
        "latitude": 19.0760,
        "longitude": 72.8777,
        "rainfall_1h_mm": 25.0,
        "rainfall_24h_mm": 110.0,
        "drainage_capacity_pct": 40.0
    })
    assert response.status_code == 200
    data = response.json()
    assert "flood_probability" in data
    assert "flood_risk_level" in data
    assert "estimated_inundation_depth_m" in data
    assert "contributing_factors" in data

def test_hotspots_endpoint(client):
    """Test /hotspots micro-grid scanning endpoint."""
    response = client.get("/hotspots?lat=19.0760&lon=72.8777&radius_km=5&grid_size_km=1.0&min_risk=0.4")
    assert response.status_code == 200
    data = response.json()
    assert "total_cells_scanned" in data
    assert "hotspots_identified" in data
    assert isinstance(data["hotspots"], list)

def test_ward_readiness_endpoint(client):
    """Test /wards/readiness municipal preparedness grading endpoint."""
    response = client.get("/wards/readiness?lat=19.0760&lon=72.8777&radius_km=10")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0
    first_ward = data[0]
    assert "ward_id" in first_ward
    assert "readiness_grade" in first_ward
    assert first_ward["readiness_grade"] in ["A", "B", "C", "D", "F"]

def test_nowcast_endpoint(client):
    """Test /nowcast short-range forecasting endpoint."""
    response = client.get("/nowcast?lat=19.0760&lon=72.8777&horizon_minutes=45")
    assert response.status_code == 200
    data = response.json()
    assert "nowcast_horizon_minutes" in data
    assert "flood_probability" in data
    assert "flood_risk_level" in data

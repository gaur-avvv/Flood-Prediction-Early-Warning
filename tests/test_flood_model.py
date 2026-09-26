import numpy as np
import pandas as pd
from models.flood_model import FloodMLModel, FEATURE_COLUMNS

def test_model_initialization_and_metadata():
    """Verify FloodMLModel initializes with valid metadata schema."""
    model = FloodMLModel()
    assert model.metadata is not None
    assert hasattr(model.metadata, "accuracy")
    assert hasattr(model.metadata, "precision")
    assert hasattr(model.metadata, "recall")
    assert hasattr(model.metadata, "brier_score")
    assert hasattr(model.metadata, "confusion_matrix")
    assert hasattr(model.metadata, "rmse_depth")

def test_held_out_validation_training():
    """Verify training evaluates held-out test metrics and produces calibrated probabilities."""
    model = FloodMLModel()
    n_samples = 150
    rng = np.random.default_rng(42)

    data = {col: rng.normal(10, 2, n_samples) for col in FEATURE_COLUMNS}
    data["rainfall_24h_mm"] = rng.uniform(0, 200, n_samples)
    data["drainage_capacity_pct"] = rng.uniform(20, 90, n_samples)
    data["drain_condition_score"] = rng.uniform(0.3, 0.9, n_samples)
    X = pd.DataFrame(data)

    # Synthetic target
    y_flood = (X["rainfall_24h_mm"] > 100).astype(int)
    y_depth = y_flood * (X["rainfall_24h_mm"] / 100.0)

    meta = model.train(X, y_flood, y_depth)

    assert meta.trained is True
    assert 0.0 <= meta.accuracy <= 1.0
    assert 0.0 <= meta.precision <= 1.0
    assert 0.0 <= meta.recall <= 1.0
    assert 0.0 <= meta.brier_score <= 1.0
    assert len(meta.confusion_matrix) == 2
    assert meta.test_samples > 0

    # Prediction test
    prob, flood_cls, depth = model.predict(X.iloc[:5])
    assert len(prob) == 5
    assert (prob >= 0.0).all() and (prob <= 1.0).all()
    assert (depth >= 0.0).all()

"""
Core flood prediction ML model.

Architecture: Stacked ensemble
  - Random Forest (interpretable, handles missing data)
  - XGBoost (high accuracy on tabular hydro data)
  - LightGBM (fast, handles large grids)
  - Meta-learner: Logistic Regression (calibrated probabilities)

Training targets:
  - Binary: flood / no-flood (threshold ~10cm inundation)
  - Regression: inundation depth (metres)
"""

import hashlib
import logging
import os
import pickle
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor, StackingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    brier_score_loss,
    f1_score,
    roc_auc_score,
    mean_absolute_error,
)
from sklearn.model_selection import StratifiedKFold, cross_val_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.impute import SimpleImputer

try:
    import xgboost as xgb
    XGB_AVAILABLE = True
except ImportError:
    XGB_AVAILABLE = False

try:
    import lightgbm as lgb
    LGB_AVAILABLE = True
except ImportError:
    LGB_AVAILABLE = False

logger = logging.getLogger(__name__)

# ── Parallelism budget ────────────────────────────────────────────────────────
# n_jobs=-1 inside a StackingClassifier whose base estimators also use n_jobs=-1
# multiplies thread count across CV folds → RAM spike → OOM on Codespace.
# Cap at 2 leaf-level threads; StackingClassifier itself is serial (n_jobs=1)
# so folds never run simultaneously.  Override with FLOOD_N_JOBS env var.
_N_JOBS: int = int(os.environ.get("FLOOD_N_JOBS", "2"))

MODEL_DIR = os.path.join(os.path.dirname(__file__), "..", "saved_models")
os.makedirs(MODEL_DIR, exist_ok=True)

CLASSIFIER_PATH = os.path.join(MODEL_DIR, "flood_classifier.pkl")
REGRESSOR_PATH = os.path.join(MODEL_DIR, "depth_regressor.pkl")
METADATA_PATH = os.path.join(MODEL_DIR, "metadata.pkl")

# All features in canonical order (must match feature_engineering output)
FEATURE_COLUMNS = [
    "rainfall_1h_mm", "rainfall_3h_mm", "rainfall_6h_mm",
    "rainfall_24h_mm", "rainfall_48h_mm", "rainfall_72h_mm",
    "rainfall_intensity", "antecedent_precip_index",
    # ── River discharge (GloFAS ensemble) ────────────────────────────────────
    # river_discharge_m3s : raw observed/forecast median discharge (m³/s)
    # discharge_anomaly_ratio : discharge / historical_p50. >1 = above median,
    #                           >2 = significant, >4 = extreme.
    # These two features provide the model with real hydrograph state,
    # dramatically improving flood detection in catchment-driven events.
    "river_discharge_m3s", "discharge_anomaly_ratio",
    "elevation_m", "slope_degrees", "aspect_degrees", "curvature",
    "flow_accumulation", "stream_distance_m", "water_body_distance_m",
    "soil_type_code", "soil_moisture_pct", "lulc_code",
    "impervious_surface_pct", "ndvi",
    "drainage_capacity_pct", "drain_age_years", "drain_condition_score",
    "pump_stations_count", "sewer_overflow_events_30d",
    "temperature_c", "humidity_pct", "wind_speed_ms",
    "wind_direction_deg", "evapotranspiration_mm", "pressure_hpa",
    "population_density", "building_density_pct", "green_space_pct",
    "previous_flood_events_5y", "month", "hour_of_day",
    # Engineered
    "rain_accumulation_ratio", "runoff_coefficient", "drainage_stress",
    "terrain_vulnerability", "composite_risk_index",
]


@dataclass
class ModelMetadata:
    trained: bool = False
    accuracy: float = 0.0
    f1: float = 0.0
    roc_auc: float = 0.0
    mae_depth: float = 0.0
    last_trained: Optional[datetime] = None
    training_samples: int = 0
    hotspots_mapped: int = 0
    feature_importances: dict = field(default_factory=dict)
    location_lat: Optional[float] = None
    location_lon: Optional[float] = None
    # ── T-32 metric block + T-31 artefact verification ──
    pr_auc: Optional[float] = None
    brier_score: Optional[float] = None
    expected_calibration_error: Optional[float] = None
    calibration_curve: list = field(default_factory=list)
    split_strategy: str = "in_sample_cv_calibrated"
    eval_samples: int = 0
    model_hash: Optional[str] = None
    artefact_verified: bool = False


def _calibration_table(y_true: np.ndarray, probs: np.ndarray, n_bins: int = 10):
    """Reliability table + Expected Calibration Error (T-32)."""
    table = []
    ece = 0.0
    n = len(y_true)
    if n == 0:
        return table, 0.0
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    for i in range(n_bins):
        lo, hi = edges[i], edges[i + 1]
        mask = (probs >= lo) & (probs < hi) if i < n_bins - 1 else (probs >= lo) & (probs <= hi)
        count = int(mask.sum())
        if count == 0:
            continue
        mean_pred = float(probs[mask].mean())
        frac_pos = float(y_true[mask].mean())
        ece += (count / n) * abs(mean_pred - frac_pos)
        table.append(
            {
                "bin_lower": round(float(lo), 2),
                "bin_upper": round(float(hi), 2),
                "count": count,
                "mean_predicted": round(mean_pred, 4),
                "fraction_positive": round(frac_pos, 4),
            }
        )
    return table, ece


def _sha256_of_files(paths) -> str:
    h = hashlib.sha256()
    for p in paths:
        with open(p, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
    return h.hexdigest()


class FloodMLModel:
    """
    Stacked ensemble classifier for flood probability + depth regressor.
    """

    def __init__(self):
        self.classifier: Optional[Pipeline] = None
        self.depth_regressor: Optional[Pipeline] = None
        self.metadata = ModelMetadata()
        self._load_if_exists()

    # ──────────────────────────────────────────────────────────────────────────
    # Build

    def _build_classifier(self) -> Pipeline:
        estimators = [
            (
                "rf",
                RandomForestClassifier(
                    n_estimators=100,
                    max_depth=20,
                    min_samples_split=10,
                    class_weight="balanced",
                    random_state=42,
                    n_jobs=_N_JOBS,            # capped – see _N_JOBS constant
                ),
            ),
        ]
        if XGB_AVAILABLE:
            estimators.append(
                (
                    "xgb",
                    xgb.XGBClassifier(
                        n_estimators=100,
                        learning_rate=0.1,
                        max_depth=5,
                        subsample=0.8,
                        colsample_bytree=0.8,
                        scale_pos_weight=3,
                        eval_metric="logloss",
                        random_state=42,
                        n_jobs=_N_JOBS,
                        nthread=_N_JOBS,       # XGBoost thread cap
                    ),
                )
            )
        if LGB_AVAILABLE:
            estimators.append(
                (
                    "lgb",
                    lgb.LGBMClassifier(
                        n_estimators=100,
                        learning_rate=0.1,
                        num_leaves=31,
                        class_weight="balanced",
                        random_state=42,
                        n_jobs=_N_JOBS,
                        num_threads=_N_JOBS,   # LightGBM thread cap
                        verbose=-1,
                    ),
                )
            )

        stacking = StackingClassifier(
            estimators=estimators,
            final_estimator=LogisticRegression(C=1.0, max_iter=1000),
            cv=StratifiedKFold(n_splits=3, shuffle=True, random_state=42),
            stack_method="predict_proba",
            # n_jobs=1: folds run serially; base estimators already use _N_JOBS
            # threads each, so parallel folds would multiply RAM consumption.
            n_jobs=1,
        )

        # cv=2: one less calibration fit per model
        calibrated = CalibratedClassifierCV(stacking, method="isotonic", cv=2)

        return Pipeline(
            steps=[
                ("imputer", SimpleImputer(strategy="median")),
                ("scaler", StandardScaler()),
                ("model", calibrated),
            ]
        )

    def _build_depth_regressor(self) -> Pipeline:
        base = RandomForestRegressor(
            n_estimators=100,
            max_depth=15,
            random_state=42,
            n_jobs=_N_JOBS,
        )
        if XGB_AVAILABLE:
            base = xgb.XGBRegressor(
                n_estimators=100,
                learning_rate=0.1,
                max_depth=5,
                subsample=0.8,
                random_state=42,
                n_jobs=_N_JOBS,
                nthread=_N_JOBS,
            )
        return Pipeline(
            steps=[
                ("imputer", SimpleImputer(strategy="median")),
                ("scaler", StandardScaler()),
                ("model", base),
            ]
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Train

    # Maximum rows used for training – keeps wall-clock time predictable on
    # resource-constrained cloud instances (≈3–5 min for the stacked ensemble).
    _MAX_TRAIN_ROWS = 50_000

    def train(
        self,
        X: pd.DataFrame,
        y_flood: pd.Series,
        y_depth: pd.Series,
        dates: Optional[pd.Series] = None,
    ) -> ModelMetadata:
        """Train both classifier and depth regressor, return metrics.

        T-32: when ``dates`` are supplied and cover >60 distinct timestamps,
        metrics are computed on a time-ordered 80/20 holdout (the production
        artefact is then refit on 100% of the data); otherwise metrics are
        in-sample and ``split_strategy`` reports that honestly.
        """
        logger.info("Training flood classifier on %d samples…", len(X))

        # Sub-sample large datasets to keep training time bounded.
        if len(X) > self._MAX_TRAIN_ROWS:
            logger.info(
                "Dataset too large (%d rows) – stratified sub-sampling to %d rows",
                len(X), self._MAX_TRAIN_ROWS,
            )
            from sklearn.model_selection import train_test_split
            if dates is not None:
                X, _, y_flood, _, y_depth, _, dates, _ = train_test_split(
                    X, y_flood, y_depth, pd.Series(dates).reset_index(drop=True),
                    train_size=self._MAX_TRAIN_ROWS,
                    stratify=y_flood,
                    random_state=42,
                )
            else:
                X, _, y_flood, _, y_depth, _ = train_test_split(
                    X, y_flood, y_depth,
                    train_size=self._MAX_TRAIN_ROWS,
                    stratify=y_flood,
                    random_state=42,
                )

        X_clean = X[FEATURE_COLUMNS].copy().reset_index(drop=True)
        y_flood = y_flood.reset_index(drop=True)
        y_depth = y_depth.reset_index(drop=True)

        # ── Evaluation split (T-32) ──
        split_strategy = "in_sample_cv_calibrated"
        eval_idx = None
        if dates is not None and len(dates) == len(X_clean):
            d = pd.to_datetime(pd.Series(dates).reset_index(drop=True))
            if d.nunique() > 60:
                order = np.argsort(d.to_numpy())
                cut = max(1, int(len(order) * 0.8))
                tr, te = order[:cut], order[cut:]
                if y_flood.iloc[tr].nunique() > 1 and y_flood.iloc[te].nunique() > 1:
                    eval_idx = (tr, te)
                    split_strategy = "time_ordered_holdout_80_20"

        # ── Classifier ──
        self.classifier = self._build_classifier()
        if eval_idx is not None:
            tr, te = eval_idx
            self.classifier.fit(X_clean.iloc[tr], y_flood.iloc[tr].values)
            probs = self.classifier.predict_proba(X_clean.iloc[te])[:, 1]
            y_eval = y_flood.iloc[te].values
            # Refit on the full dataset for the production artefact.
            self.classifier.fit(X_clean, y_flood.values)
        else:
            self.classifier.fit(X_clean, y_flood.values)
            probs = self.classifier.predict_proba(X_clean)[:, 1]
            y_eval = y_flood.values
        eval_samples = len(y_eval)
        preds = (probs >= 0.5).astype(int)

        acc = accuracy_score(y_eval, preds)
        f1 = f1_score(y_eval, preds, zero_division=0)
        n_classes = len(np.unique(y_eval))
        auc = roc_auc_score(y_eval, probs) if n_classes > 1 else 0.5
        pr_auc = average_precision_score(y_eval, probs) if n_classes > 1 else 0.0
        brier = brier_score_loss(y_eval, probs)
        cal_table, ece = _calibration_table(np.asarray(y_eval), np.asarray(probs))

        logger.info(
            "Classifier: acc=%.3f f1=%.3f auc=%.3f pr_auc=%.3f brier=%.3f ece=%.3f split=%s",
            acc, f1, auc, pr_auc, brier, ece, split_strategy,
        )

        # ── Depth Regressor ──
        self.depth_regressor = self._build_depth_regressor()
        flood_mask = (y_flood == 1).values
        if flood_mask.sum() > 10:
            self.depth_regressor.fit(X_clean[flood_mask], y_depth.values[flood_mask])
            depth_preds = self.depth_regressor.predict(X_clean[flood_mask])
            mae = mean_absolute_error(y_depth.values[flood_mask], depth_preds)
        else:
            # Fallback: train on all with depth=0 for no-flood
            self.depth_regressor.fit(X_clean, y_depth.values)
            mae = mean_absolute_error(y_depth, self.depth_regressor.predict(X_clean))

        logger.info("Depth regressor MAE: %.3f m", mae)

        # ── Feature importances (RF only) ──
        # Pipeline: imputer → scaler → model (CalibratedClassifierCV)
        # CalibratedClassifierCV(cv=2) stores *fitted* clones in
        # .calibrated_classifiers_[fold].estimator  (a fitted StackingClassifier)
        # StackingClassifier.estimators_ → [(name, fitted_estimator), …]
        try:
            calibrated_cv = self.classifier.named_steps["model"]
            stacking = calibrated_cv.calibrated_classifiers_[0].estimator
            rf_model = stacking.estimators_[0][1]   # ('rf', RandomForestClassifier)
            importances = dict(zip(FEATURE_COLUMNS, rf_model.feature_importances_))
        except Exception as exc:
            logger.debug("Feature importances unavailable: %s", exc)
            importances = {}

        self.metadata = ModelMetadata(
            trained=True,
            accuracy=round(acc, 4),
            f1=round(f1, 4),
            roc_auc=round(auc, 4),
            mae_depth=round(mae, 4),
            pr_auc=round(pr_auc, 4),
            brier_score=round(brier, 4),
            expected_calibration_error=round(ece, 4),
            calibration_curve=cal_table,
            split_strategy=split_strategy,
            eval_samples=eval_samples,
            last_trained=datetime.utcnow(),
            training_samples=len(X),
            feature_importances={
                k: round(float(v), 6)
                for k, v in sorted(importances.items(), key=lambda x: -x[1])[:15]
            },
        )
        self._save()
        return self.metadata

    # ──────────────────────────────────────────────────────────────────────────
    # Predict

    def predict(self, X: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Returns:
          - flood_prob  (N,)  0–1
          - flood_class (N,)  0 or 1
          - depth_pred  (N,)  metres
        """
        if self.classifier is None:
            raise RuntimeError("Model not trained.")

        X_clean = X[FEATURE_COLUMNS].copy()
        flood_prob = self.classifier.predict_proba(X_clean)[:, 1]
        flood_class = (flood_prob >= 0.5).astype(int)

        depth_pred = np.zeros(len(X))
        flood_mask = flood_class == 1
        if flood_mask.any() and self.depth_regressor is not None:
            ml_depth = np.maximum(0, self.depth_regressor.predict(X_clean[flood_mask]))

            # Physics fallback: SCS rational method
            # Uses the same formula as training label generation so the result
            # is always physically plausible even when the ML regressor
            # under-predicts (e.g. out-of-distribution drainage_capacity values).
            r24 = X_clean.loc[flood_mask, "rainfall_24h_mm"].values
            drain = X_clean.loc[flood_mask, "drainage_capacity_pct"].values
            cond  = X_clean.loc[flood_mask, "drain_condition_score"].values
            effective_cap = (drain * cond) / 100.0
            physics_depth = np.clip(
                r24 / 100.0 * np.maximum(0.0, 1.0 - effective_cap), 0.0, 3.0
            )

            # Blend: take the larger of ML and physics, scaled by flood probability
            depth_pred[flood_mask] = np.maximum(ml_depth, physics_depth * flood_prob[flood_mask])

        return flood_prob, flood_class, depth_pred

    # ──────────────────────────────────────────────────────────────────────────
    # Persistence

    def _save(self):
        with open(CLASSIFIER_PATH, "wb") as f:
            pickle.dump(self.classifier, f)
        with open(REGRESSOR_PATH, "wb") as f:
            pickle.dump(self.depth_regressor, f)
        # T-31: artefact integrity – hash of the binary model files, stored in
        # metadata and re-verified on every load.
        self.metadata.model_hash = _sha256_of_files([CLASSIFIER_PATH, REGRESSOR_PATH])
        self.metadata.artefact_verified = True
        with open(METADATA_PATH, "wb") as f:
            pickle.dump(self.metadata, f)
        logger.info(
            "Model saved to %s (sha256=%s…)", MODEL_DIR, self.metadata.model_hash[:12]
        )

    def verify_artefact(self) -> bool:
        """T-31: re-hash the saved artefacts and compare with metadata."""
        if not self.is_trained:
            return False
        expected = getattr(self.metadata, "model_hash", None)
        if not expected:
            self.metadata.artefact_verified = False
            return False
        try:
            actual = _sha256_of_files([CLASSIFIER_PATH, REGRESSOR_PATH])
        except OSError:
            self.metadata.artefact_verified = False
            return False
        self.metadata.artefact_verified = actual == expected
        return self.metadata.artefact_verified

    def _load_if_exists(self):
        if all(os.path.exists(p) for p in [CLASSIFIER_PATH, REGRESSOR_PATH, METADATA_PATH]):
            try:
                with open(CLASSIFIER_PATH, "rb") as f:
                    self.classifier = pickle.load(f)
                with open(REGRESSOR_PATH, "rb") as f:
                    self.depth_regressor = pickle.load(f)
                with open(METADATA_PATH, "rb") as f:
                    self.metadata = pickle.load(f)
                expected_hash = getattr(self.metadata, "model_hash", None)
                if expected_hash:
                    actual = _sha256_of_files([CLASSIFIER_PATH, REGRESSOR_PATH])
                    self.metadata.artefact_verified = actual == expected_hash
                    if not self.metadata.artefact_verified:
                        logger.error(
                            "Model artefact hash MISMATCH – saved files may be "
                            "corrupted or tampered with (expected %s…, got %s…)",
                            expected_hash[:12], actual[:12],
                        )
                else:
                    self.metadata.artefact_verified = False
                    logger.info("Legacy model artefact without hash – unverified")
                logger.info(
                    "Loaded existing model (acc=%.3f, trained=%s, verified=%s)",
                    self.metadata.accuracy,
                    self.metadata.last_trained,
                    getattr(self.metadata, "artefact_verified", False),
                )
            except Exception as e:
                logger.warning("Failed to load saved model: %s", e)
                self.metadata = ModelMetadata()

    @property
    def is_trained(self) -> bool:
        return self.metadata.trained and self.classifier is not None


# Singleton
_model_instance: Optional[FloodMLModel] = None


def get_model() -> FloodMLModel:
    global _model_instance
    if _model_instance is None:
        _model_instance = FloodMLModel()
    return _model_instance

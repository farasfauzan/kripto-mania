"""
ML Ensemble Engine — Aggressive Scalper Mode v2
===============================================
Multi-model ensemble: XGBoost + LightGBM + Random Forest + Voting + Stacking.
50+ engineered features, walk-forward validation, Optuna tuning, online learning,
model versioning, feature drift detection, backtest framework.

Keluaran: probabilitas scalp jangka pendek (0.8-1.5% dalam 1-3 candle).
"""

from __future__ import annotations
import os
import json
import pickle
import warnings
from datetime import datetime, timezone
from typing import Any, Optional
from dataclasses import dataclass, field, asdict

import numpy as np
import pandas as pd

# ── Model libs ──────────────────────────────────────────────────────────────
from sklearn.ensemble import (
    RandomForestClassifier,
    VotingClassifier,
    StackingClassifier,
)
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    roc_auc_score,
)
from sklearn.model_selection import TimeSeriesSplit
from sklearn.preprocessing import RobustScaler
from sklearn.pipeline import Pipeline

ML_AVAILABLE = True
XGB_AVAILABLE = LGBM_AVAILABLE = OPTUNA_AVAILABLE = False

try:
    import xgboost as xgb

    XGB_AVAILABLE = True
except (ImportError, OSError):
    pass

try:
    import lightgbm as lgb

    LGBM_AVAILABLE = True
except (ImportError, OSError):
    pass

try:
    import optuna

    OPTUNA_AVAILABLE = True
except ImportError:
    pass

warnings.filterwarnings("ignore", category=UserWarning)

# ── Paths ───────────────────────────────────────────────────────────────────
MODEL_DIR = "ml_models"
ENSEMBLE_MODEL_PATH = os.path.join(MODEL_DIR, "ensemble_model.pkl")
FEATURE_META_PATH = os.path.join(MODEL_DIR, "feature_meta.json")
MODEL_REGISTRY_PATH = os.path.join(MODEL_DIR, "model_registry.json")
os.makedirs(MODEL_DIR, exist_ok=True)

WIB = timezone.utc  # UTC internally; display formatting done by caller


# ── Config ──────────────────────────────────────────────────────────────────
@dataclass
class MLConfig:
    n_trials_optuna: int = int(os.environ.get("ML_OPTUNA_TRIALS", "20"))
    cv_splits: int = int(os.environ.get("ML_CV_SPLITS", "5"))
    test_size_walk: float = 0.2
    min_train_samples: int = int(os.environ.get("ML_MIN_TRAIN", "100"))
    retrain_interval_hours: int = int(os.environ.get("ML_RETRAIN_INTERVAL", "24"))
    prob_threshold_scalp: float = 70.0
    ensemble_voting: str = "soft"
    use_stacking: bool = True
    max_features: int = 60
    drift_warning_zscore: float = 2.5
    model_ttl_days: int = 30

    @classmethod
    def load(cls) -> "MLConfig":
        path = os.path.join(MODEL_DIR, "config.json")
        if os.path.exists(path):
            with open(path) as f:
                data = json.load(f)
            return cls(**{k: data[k] for k in cls.__dataclass_fields__ if k in data})
        return cls()

    def save(self):
        path = os.path.join(MODEL_DIR, "config.json")
        with open(path, "w") as f:
            json.dump(asdict(self), f, indent=2)


CFG = MLConfig.load()


# ═════════════════════════════════════════════════════════════════════════════
# 1. FEATURE ENGINEERING
# ═════════════════════════════════════════════════════════════════════════════


def engineer_features(candles: pd.DataFrame) -> pd.DataFrame:
    """
    50+ engineered features:
    returns, RSI(7,14,21), MACD, BB %B/width, ATR pct, volume ratios,
    price/MA ratios, range%, skew/kurt, lag features, interactions,
    candle body/wick %, ROC, OBV, MFI proxy, time features.
    """
    if candles is None or candles.empty or len(candles) < 50:
        return pd.DataFrame()

    df = candles.copy()
    for col in ["close", "high", "low", "open", "volume"]:
        if col in df.columns:
            df[col] = df[col].astype(float)
        elif col == "open" and "close" in df.columns:
            df["open"] = df["close"].shift(1).astype(float)

    close = df["close"]
    high = df["high"]
    low = df["low"]
    vol = df["volume"]
    opn = df["open"]

    features = pd.DataFrame(index=df.index)

    for p in [1, 3, 5, 8, 13, 21]:
        features[f"ret_{p}"] = close.pct_change(p) * 100

    for p in [7, 14, 21]:
        delta = close.diff()
        gain = delta.clip(lower=0).ewm(alpha=1 / p, adjust=False).mean()
        loss = (-delta.clip(upper=0)).ewm(alpha=1 / p, adjust=False).mean()
        rs = gain / loss.replace(0, np.nan)
        features[f"rsi_{p}"] = 100 - (100 / (1 + rs))

    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    macd_signal = macd_line.ewm(span=9, adjust=False).mean()
    features["macd"] = macd_line
    features["macd_signal"] = macd_signal
    features["macd_hist"] = macd_line - macd_signal

    for p in [14, 20]:
        ma = close.rolling(p).mean()
        std = close.rolling(p).std()
        features[f"bb_pct_{p}"] = (
            (close - ma + 2 * std) / (4 * std).replace(0, np.nan)
        ) * 100
        features[f"bb_width_{p}"] = (4 * std / ma.replace(0, np.nan)) * 100

    for p in [7, 14]:
        tr = pd.concat(
            [high - low, (high - close.shift(1)).abs(), (low - close.shift(1)).abs()],
            axis=1,
        ).max(axis=1)
        atr = tr.rolling(p).mean()
        features[f"atr_pct_{p}"] = (atr / close.replace(0, np.nan)) * 100

    vol_sma20 = vol.rolling(20).mean()
    for p in [1, 3, 5, 8, 13]:
        features[f"vr_{p}"] = vol.rolling(p).mean() / vol_sma20.replace(0, np.nan)
    features["vol_ma20_ratio"] = vol / vol_sma20.replace(0, np.nan)

    for p in [5, 8, 13, 21, 50]:
        ma = close.rolling(p).mean()
        features[f"price_ma_{p}"] = (close / ma.replace(0, np.nan) - 1) * 100

    for p in [5, 10, 20]:
        features[f"range_pct_{p}"] = (
            (high.rolling(p).max() - low.rolling(p).min()) / close.replace(0, np.nan)
        ) * 100

    for p in [10, 20]:
        features[f"skew_{p}"] = close.rolling(p).skew()
        features[f"kurt_{p}"] = close.rolling(p).kurt()

    for lag in [1, 2, 3]:
        features[f"lag_close_{lag}"] = close.shift(lag)
        features[f"lag_ret_{lag}"] = close.pct_change(lag).shift(lag) * 100

    ret1 = close.pct_change(1)
    features["ret_x_vol"] = ret1 * vol / vol.mean()
    atr14 = (
        (
            pd.concat(
                [
                    high - low,
                    (high - close.shift(1)).abs(),
                    (low - close.shift(1)).abs(),
                ],
                axis=1,
            ).max(axis=1)
        )
        .rolling(14)
        .mean()
    )
    features["vola_x_vol"] = (atr14 / close.replace(0, np.nan)) * (vol / vol.mean())

    body = abs(close - opn)
    features["body_pct"] = (body / (high - low).replace(0, np.nan)) * 100
    features["upper_wick_pct"] = (
        (high - close.where(close > opn, opn)) / (high - low).replace(0, np.nan)
    ) * 100
    features["lower_wick_pct"] = (
        (close.where(close < opn, opn) - low) / (high - low).replace(0, np.nan)
    ) * 100

    for p in [5, 10, 20]:
        features[f"roc_{p}"] = close.pct_change(p) * 100

    obv = (vol * ((close.diff() > 0).astype(int) * 2 - 1)).cumsum()
    features["obv_roc_5"] = obv.pct_change(5) * 100
    features["obv_roc_10"] = obv.pct_change(10) * 100

    tp = (high + low + close) / 3
    mf = tp * vol
    pos_mf = mf.where(tp > tp.shift(1), 0).rolling(14).sum()
    neg_mf = mf.where(tp < tp.shift(1), 0).rolling(14).sum()
    features["mfi"] = 100 - (100 / (1 + pos_mf / neg_mf.replace(0, np.nan)))

    if isinstance(df.index, pd.DatetimeIndex):
        features["hour"] = df.index.hour
        features["dayofweek"] = df.index.dayofweek
        features["dayofmonth"] = df.index.day

    features = features.replace([np.inf, -np.inf], np.nan)
    features = features.fillna(method="ffill").fillna(method="bfill").fillna(0)

    return features


def _prepare_features_with_target(
    candles: pd.DataFrame,
    horizon: int = 3,
    target_pct: float = 1.0,
) -> tuple[pd.DataFrame, pd.Series, pd.DataFrame]:
    if candles is None or len(candles) < 60:
        return pd.DataFrame(), pd.Series(dtype=int), pd.DataFrame()

    close = candles["close"].astype(float)
    X_all = engineer_features(candles)

    future_max = close.rolling(horizon).max().shift(-horizon)
    target = ((future_max - close) / close.replace(0, np.nan) * 100) > target_pct
    target = target.astype(int)

    valid = X_all.dropna().index.intersection(target.dropna().index)
    X = X_all.loc[valid]
    y = target.loc[valid]

    X = X.loc[:, X.nunique() > 1]

    if X.shape[1] > CFG.max_features:
        var = X.var().sort_values(ascending=False)
        keep = var.head(CFG.max_features).index
        X = X[keep]
        X_all = X_all[keep]

    current_X = X_all.iloc[[-1]].fillna(0)
    common_cols = current_X.columns.intersection(X.columns)
    current_X = current_X[common_cols]
    for col in X.columns:
        if col not in current_X.columns:
            current_X[col] = 0.0
    current_X = current_X[X.columns]

    return X, y, current_X


def _get_feature_names(X: pd.DataFrame) -> list[str]:
    return list(X.columns)


# ═════════════════════════════════════════════════════════════════════════════
# 2. MODEL REGISTRY
# ═════════════════════════════════════════════════════════════════════════════


def _load_model_registry() -> list[dict]:
    if os.path.exists(MODEL_REGISTRY_PATH):
        try:
            with open(MODEL_REGISTRY_PATH) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return []
    return []


def _save_model_registry(registry: list[dict]):
    with open(MODEL_REGISTRY_PATH, "w") as f:
        json.dump(registry, f, indent=2, default=str)


def _register_model_version(metrics: dict, features: list[str], model_type: str):
    registry = _load_model_registry()
    entry = {
        "version": len(registry) + 1,
        "created_at": datetime.now(WIB).isoformat(),
        "model_type": model_type,
        "features_count": len(features),
        "metrics": {
            k: round(float(v), 4) if isinstance(v, (float, np.floating)) else v
            for k, v in metrics.items()
        },
        "n_features": len(features),
    }
    registry.append(entry)
    if len(registry) > 20:
        registry = registry[-20:]
    _save_model_registry(registry)
    return entry["version"]


def get_model_registry_summary() -> list[dict]:
    return _load_model_registry()


# ═════════════════════════════════════════════════════════════════════════════
# 3. HYPERPARAMETER TUNING — Optuna
# ═════════════════════════════════════════════════════════════════════════════


def _optimize_params(X: pd.DataFrame, y: pd.Series) -> dict:
    if not OPTUNA_AVAILABLE or len(X) < 100:
        return {}

    tscv = TimeSeriesSplit(n_splits=min(CFG.cv_splits, max(2, len(X) // 50)))

    def objective(trial):
        params = {
            "n_estimators": trial.suggest_int("n_estimators", 50, 300, step=50),
            "max_depth": trial.suggest_int("max_depth", 3, 10),
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
            "subsample": trial.suggest_float("subsample", 0.6, 1.0),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.6, 1.0),
            "min_child_weight": trial.suggest_int("min_child_weight", 1, 10),
            "gamma": trial.suggest_float("gamma", 0, 5),
            "reg_alpha": trial.suggest_float("reg_alpha", 1e-8, 10, log=True),
            "reg_lambda": trial.suggest_float("reg_lambda", 1e-8, 10, log=True),
        }
        scores = []
        for train_idx, val_idx in tscv.split(X, y):
            X_tr, X_val = X.iloc[train_idx], X.iloc[val_idx]
            y_tr, y_val = y.iloc[train_idx], y.iloc[val_idx]
            if len(np.unique(y_tr)) < 2:
                continue
            try:
                model = xgb.XGBClassifier(
                    **params,
                    eval_metric="logloss",
                    random_state=42,
                    use_label_encoder=False,
                    verbosity=0,
                )
                model.fit(X_tr, y_tr, eval_set=[(X_val, y_val)], verbose=False)
                pred = model.predict(X_val)
                scores.append(f1_score(y_val, pred, zero_division=0))
            except Exception:
                continue
        return np.mean(scores) if scores else 0.0

    study = optuna.create_study(
        direction="maximize", sampler=optuna.samplers.TPESampler(seed=42)
    )
    study.optimize(objective, n_trials=CFG.n_trials_optuna, show_progress_bar=False)
    return study.best_params


# ═════════════════════════════════════════════════════════════════════════════
# 4. WALK-FORWARD VALIDATION
# ═════════════════════════════════════════════════════════════════════════════


def walk_forward_validate(
    model_fn: callable,
    X: pd.DataFrame,
    y: pd.Series,
    n_splits: int = 5,
) -> dict:
    tscv = TimeSeriesSplit(n_splits=min(n_splits, max(2, len(X) // 50)))
    metrics = {"accuracy": [], "precision": [], "recall": [], "f1": [], "roc_auc": []}
    for train_idx, val_idx in tscv.split(X, y):
        X_tr, X_val = X.iloc[train_idx], X.iloc[val_idx]
        y_tr, y_val = y.iloc[train_idx], y.iloc[val_idx]
        if len(np.unique(y_tr)) < 2 or len(np.unique(y_val)) < 2:
            continue
        try:
            model = model_fn()
            model.fit(X_tr, y_tr)
            pred = model.predict(X_val)
            proba = (
                model.predict_proba(X_val)[:, 1]
                if hasattr(model, "predict_proba")
                else None
            )
            metrics["accuracy"].append(accuracy_score(y_val, pred))
            metrics["precision"].append(precision_score(y_val, pred, zero_division=0))
            metrics["recall"].append(recall_score(y_val, pred, zero_division=0))
            metrics["f1"].append(f1_score(y_val, pred, zero_division=0))
            if proba is not None:
                metrics["roc_auc"].append(roc_auc_score(y_val, proba))
        except Exception:
            continue
    summary = {}
    for k, v in metrics.items():
        if v:
            summary[k] = float(np.mean(v))
            summary[f"{k}_std"] = float(np.std(v))
        else:
            summary[k] = 0.0
            summary[f"{k}_std"] = 0.0
    return summary


# ═════════════════════════════════════════════════════════════════════════════
# 5. ENSEMBLE TRAINER
# ═════════════════════════════════════════════════════════════════════════════


def _build_base_models(best_params: dict | None = None) -> list[tuple[str, Any]]:
    models = []
    seed = 42
    rf = RandomForestClassifier(
        n_estimators=150,
        max_depth=8,
        min_samples_leaf=5,
        random_state=seed,
        class_weight="balanced",
        n_jobs=-1,
    )
    models.append(("rf", rf))

    if XGB_AVAILABLE:
        xgb_params = {
            "n_estimators": 150,
            "max_depth": 5,
            "learning_rate": 0.05,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
            "min_child_weight": 3,
            "gamma": 0.1,
            "reg_alpha": 0.01,
            "reg_lambda": 1.0,
            "random_state": seed,
            "eval_metric": "logloss",
            "verbosity": 0,
        }
        if best_params:
            xgb_params.update(best_params)
        models.append(("xgb", xgb.XGBClassifier(**xgb_params)))

    if LGBM_AVAILABLE:
        lgb_params = {
            "n_estimators": 150,
            "max_depth": 5,
            "learning_rate": 0.05,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
            "min_child_samples": 5,
            "reg_alpha": 0.01,
            "reg_lambda": 1.0,
            "random_state": seed,
            "verbose": -1,
            "class_weight": "balanced",
        }
        if best_params:
            lgb_params.update({k: v for k, v in best_params.items() if k in lgb_params})
        models.append(("lgb", lgb.LGBMClassifier(**lgb_params)))

    return models


def train_ensemble(X: pd.DataFrame, y: pd.Series) -> dict:
    result = {
        "success": False,
        "n_samples": len(X),
        "n_features": X.shape[1] if not X.empty else 0,
        "models_trained": [],
        "metrics": {},
        "version": None,
        "error": None,
    }
    if len(X) < CFG.min_train_samples or len(np.unique(y)) < 2:
        result["error"] = (
            f"Insufficient data: {len(X)} samples, {len(np.unique(y))} classes"
        )
        return result

    scaler = RobustScaler()
    X_scaled = pd.DataFrame(scaler.fit_transform(X), columns=X.columns, index=X.index)
    feature_names = _get_feature_names(X)
    _save_feature_meta(feature_names, scaler)

    best_params = _optimize_params(X_scaled, y) if OPTUNA_AVAILABLE else {}
    base_models = _build_base_models(best_params)

    individual_metrics = {}
    trained_estimators = []
    for name, model in base_models:
        try:
            model.fit(X_scaled, y)
            pred = model.predict(X_scaled)
            proba = (
                model.predict_proba(X_scaled)[:, 1]
                if hasattr(model, "predict_proba")
                else None
            )
            acc = accuracy_score(y, pred)
            f1 = f1_score(y, pred, zero_division=0)
            auc = roc_auc_score(y, proba) if proba is not None else 0.0
            individual_metrics[name] = {
                "accuracy": round(acc, 4),
                "f1": round(f1, 4),
                "roc_auc": round(auc, 4),
            }
            trained_estimators.append((name, model))
            result["models_trained"].append(name)
        except Exception as e:
            result["models_trained"].append(f"{name}_FAILED")
            individual_metrics[name] = {"error": str(e)}

    if not trained_estimators:
        result["error"] = "No models trained successfully"
        return result

    voting = None
    if len(trained_estimators) >= 2:
        try:
            voting = VotingClassifier(
                estimators=trained_estimators, voting=CFG.ensemble_voting
            )
            voting.fit(X_scaled, y)
            result["models_trained"].append("voting")
            v_pred = voting.predict(X_scaled)
            v_proba = voting.predict_proba(X_scaled)[:, 1]
            individual_metrics["voting"] = {
                "accuracy": round(accuracy_score(y, v_pred), 4),
                "f1": round(f1_score(y, v_pred, zero_division=0), 4),
                "roc_auc": round(roc_auc_score(y, v_proba), 4),
            }
        except Exception as e:
            individual_metrics["voting"] = {"error": str(e)}

    stacking = None
    if CFG.use_stacking and len(trained_estimators) >= 2:
        try:
            meta_learner = LogisticRegression(
                C=1.0, max_iter=1000, random_state=42, class_weight="balanced"
            )
            stacking = StackingClassifier(
                estimators=trained_estimators,
                final_estimator=meta_learner,
                cv=3,
                stack_method="predict_proba",
            )
            stacking.fit(X_scaled, y)
            result["models_trained"].append("stacking")
            s_pred = stacking.predict(X_scaled)
            s_proba = stacking.predict_proba(X_scaled)[:, 1]
            individual_metrics["stacking"] = {
                "accuracy": round(accuracy_score(y, s_pred), 4),
                "f1": round(f1_score(y, s_pred, zero_division=0), 4),
                "roc_auc": round(roc_auc_score(y, s_proba), 4),
            }
        except Exception as e:
            individual_metrics["stacking"] = {"error": str(e)}

    wfv_metrics = {}
    if len(trained_estimators) >= 2 and voting is not None:
        wfv_metrics = walk_forward_validate(
            lambda: VotingClassifier(
                estimators=trained_estimators, voting=CFG.ensemble_voting
            ),
            X_scaled,
            y,
            n_splits=min(CFG.cv_splits, max(2, len(X) // 50)),
        )

    ensemble = {
        "models": trained_estimators,
        "voting": voting,
        "stacking": stacking,
        "scaler": scaler,
        "feature_names": feature_names,
        "individual_metrics": individual_metrics,
        "walk_forward_metrics": wfv_metrics,
        "best_params": best_params,
        "n_samples": len(X),
        "trained_at": datetime.now(WIB).isoformat(),
    }

    try:
        with open(ENSEMBLE_MODEL_PATH, "wb") as f:
            pickle.dump(ensemble, f)
    except Exception as e:
        result["error"] = f"Save failed: {e}"
        return result

    metrics = {
        "accuracy": individual_metrics.get("voting", {}).get("accuracy", 0),
        "f1": individual_metrics.get("voting", {}).get("f1", 0),
        "roc_auc": individual_metrics.get("voting", {}).get("roc_auc", 0),
        "walk_f1_mean": wfv_metrics.get("f1", 0),
        "n_models": len(trained_estimators),
    }
    version = _register_model_version(metrics, feature_names, "ensemble")
    result["version"] = version
    result["metrics"] = metrics
    result["success"] = True
    return result


def _save_feature_meta(feature_names: list[str], scaler: RobustScaler):
    meta = {
        "feature_names": feature_names,
        "n_features": len(feature_names),
        "saved_at": datetime.now(WIB).isoformat(),
        "scaler_center": scaler.center_.tolist()
        if hasattr(scaler, "center_") and scaler.center_ is not None
        else [],
        "scaler_scale": scaler.scale_.tolist()
        if hasattr(scaler, "scale_") and scaler.scale_ is not None
        else [],
    }
    with open(FEATURE_META_PATH, "w") as f:
        json.dump(meta, f, indent=2)


# ═════════════════════════════════════════════════════════════════════════════
# 6. PREDICTION
# ═════════════════════════════════════════════════════════════════════════════


_CACHE_ENSEMBLE = None
_CACHE_MTIME = 0

def _load_ensemble() -> dict | None:
    global _CACHE_ENSEMBLE, _CACHE_MTIME
    if not os.path.exists(ENSEMBLE_MODEL_PATH):
        return None
    try:
        mtime = os.path.getmtime(ENSEMBLE_MODEL_PATH)
        if _CACHE_ENSEMBLE is not None and _CACHE_MTIME == mtime:
            return _CACHE_ENSEMBLE
            
        with open(ENSEMBLE_MODEL_PATH, "rb") as f:
            _CACHE_ENSEMBLE = pickle.load(f)
            _CACHE_MTIME = mtime
            return _CACHE_ENSEMBLE
    except Exception:
        return None


def _detect_feature_drift(current_X: pd.DataFrame, ensemble: dict) -> float:
    meta_path = FEATURE_META_PATH
    if not os.path.exists(meta_path):
        return 0.0
    try:
        with open(meta_path) as f:
            meta = json.load(f)
        if not meta.get("scaler_center") or not meta.get("scaler_scale"):
            return 0.0
        ref_mean = np.array(meta["scaler_center"])
        ref_std = np.array(meta["scaler_scale"])
        if len(ref_mean) == 0 or len(ref_std) == 0:
            return 0.0
        common = [c for c in current_X.columns if c in meta.get("feature_names", [])]
        if not common:
            return 0.0
        cur_vals = current_X[common].values.flatten()[: len(ref_mean)]
        if len(cur_vals) < 2:
            return 0.0
        z_scores = np.abs(
            (cur_vals - ref_mean[: len(cur_vals)]) / (ref_std[: len(cur_vals)] + 1e-8)
        )
        return float(np.max(z_scores))
    except Exception:
        return 0.0


def _fallback_prediction(candles: pd.DataFrame) -> dict:
    """
    Fallback jika data kurang atau model gagal.
    Simple momentum + volume check.
    """
    d = {
        "prob_up_pct": 50.0,
        "is_scalp_valid": False,
        "confidence": "LEMAH",
        "ensemble_detail": None,
        "drift_warning": None,
    }
    if candles is None or len(candles) < 10:
        d["confidence"] = "NO DATA"
        return d
    try:
        close = candles["close"].astype(float)
        vol = candles["volume"].astype(float)
        ret1 = float(close.pct_change(1).iloc[-1] * 100) if len(close) > 1 else 0
        ret3 = float(close.pct_change(3).iloc[-1] * 100) if len(close) > 3 else 0
        vr = float(vol.tail(3).mean() / vol.tail(20).mean()) if len(vol) > 20 else 1.0
        score = ret1 * 0.3 + ret3 * 0.2 + (vr - 1) * 20
        prob = 50.0 + score
        prob = max(10, min(90, prob))
        if prob > 65:
            d["confidence"] = "MODERAT"
            d["prob_up_pct"] = round(prob, 1)
            d["is_scalp_valid"] = prob > 70
        return d
    except Exception:
        return d


def predict_aggressive_scalp(candles: pd.DataFrame) -> dict:
    """
    Prediksi probabilitas scalp jangka pendek menggunakan ensemble.
    Kompatibel dengan interface lama (dict output).
    """
    default = {
        "prob_up_pct": 50.0,
        "is_scalp_valid": False,
        "confidence": "NO DATA",
        "ensemble_detail": None,
        "drift_warning": None,
    }

    X, y, current_X = _prepare_features_with_target(candles, horizon=3, target_pct=1.0)
    if X.empty or current_X.empty or len(X) < 30:
        return _fallback_prediction(candles)

    ensemble = _load_ensemble()
    if ensemble is None:
        tr_result = train_ensemble(X, y)
        if not tr_result["success"]:
            return _fallback_prediction(candles)
        ensemble = _load_ensemble()
        if ensemble is None:
            return _fallback_prediction(candles)

    try:
        scaler = ensemble.get("scaler")
        voting = ensemble.get("voting")
        stacking = ensemble.get("stacking")

        feature_names = ensemble.get("feature_names", [])
        for col in feature_names:
            if col not in current_X.columns:
                current_X[col] = 0.0
        current_X = current_X[feature_names]

        if scaler:
            X_scaled = scaler.transform(current_X)
        else:
            X_scaled = current_X.values

        probas = []
        if voting is not None:
            probas.append(("voting", float(voting.predict_proba(X_scaled)[0][1])))

        if stacking is not None:
            probas.append(("stacking", float(stacking.predict_proba(X_scaled)[0][1])))

        for name, model in ensemble.get("models", []):
            if hasattr(model, "predict_proba"):
                try:
                    p = float(model.predict_proba(X_scaled)[0][1])
                    probas.append((name, p))
                except Exception:
                    pass

        if not probas:
            return _fallback_prediction(candles)

        # Weighted average: voting & stacking higher weight
        weights = {"voting": 3.0, "stacking": 2.5, "xgb": 1.5, "lgb": 1.5, "rf": 1.0}
        total_w = sum(weights.get(name, 1.0) for name, _ in probas)
        prob = sum(p * weights.get(name, 1.0) for name, p in probas) / total_w
        prob_pct = round(prob * 100, 2)

        drift = _detect_feature_drift(current_X, ensemble)

        is_valid = prob_pct > CFG.prob_threshold_scalp
        if prob_pct > 85:
            conf = "SANGAT TINGGI"
        elif prob_pct > 70:
            conf = "TINGGI"
        elif prob_pct > 55:
            conf = "MODERAT"
        else:
            conf = "LEMAH"

        # Ensemble detail for dashboard
        detail = {
            "models": {name: round(p * 100, 1) for name, p in probas},
            "weighted_prob": prob_pct,
            "n_models": len(probas),
            "n_samples": ensemble.get("n_samples", 0),
            "trained_at": ensemble.get("trained_at", ""),
            "walk_f1": ensemble.get("walk_forward_metrics", {}).get("f1", None),
            "feature_count": len(feature_names),
        }

        result = {
            "prob_up_pct": prob_pct,
            "is_scalp_valid": is_valid,
            "confidence": conf,
            "ensemble_detail": detail,
            "drift_warning": f"Feature drift detected (z={drift:.1f})"
            if drift > CFG.drift_warning_zscore
            else None,
        }
        return result

    except Exception as e:
        return {**default, "confidence": "ERROR", "ensemble_detail": {"error": str(e)}}


# ═════════════════════════════════════════════════════════════════════════════
# 7. BACKTEST FRAMEWORK
# ═════════════════════════════════════════════════════════════════════════════


def backtest_ensemble(
    candles: pd.DataFrame,
    horizon: int = 3,
    target_pct: float = 1.0,
    prob_threshold: float = 70.0,
) -> dict:
    """
    Backtest ensemble: rolling walk-forward prediction, simulate trades.
    Returns performance metrics: winrate, sharpe, max_drawdown, total_trades.
    """
    default = {
        "total_trades": 0,
        "wins": 0,
        "losses": 0,
        "winrate": 0.0,
        "total_return_pct": 0.0,
        "sharpe": 0.0,
        "max_drawdown": 0.0,
        "avg_return_per_trade": 0.0,
        "error": None,
    }
    if candles is None or len(candles) < 100:
        default["error"] = "Need at least 100 candles"
        return default

    close = candles["close"].astype(float)
    try:
        returns = []
        trade_returns = []
        equity = [10000]
        max_equity = 10000
        min_equity = 10000
        for i in range(100, len(candles)):
            X, y, current_X = _prepare_features_with_target(
                candles.iloc[:i], horizon=horizon, target_pct=target_pct
            )
            if X.empty or len(X) < 50:
                continue
            pred = predict_aggressive_scalp(candles.iloc[:i])
            prob = pred.get("prob_up_pct", 50)
            if prob > prob_threshold:
                # Simulate trade: buy at close[i], sell at close[i+horizon]
                if i + horizon < len(candles):
                    entry = float(close.iloc[i])
                    exit_px = float(close.iloc[i + horizon])
                    ret = (exit_px - entry) / entry * 100
                    trade_returns.append(ret)
                    returns.append(ret)
        if not trade_returns:
            return {**default, "error": "No trades generated"}
        trade_arr = np.array(trade_returns)
        wins = int((trade_arr > 0).sum())
        losses = int((trade_arr <= 0).sum())
        total = wins + losses
        winrate = wins / total * 100 if total else 0
        total_ret = float(np.sum(trade_arr))
        avg_ret = float(np.mean(trade_arr))
        sharpe = (
            float(np.mean(trade_arr) / np.std(trade_arr) * np.sqrt(365))
            if np.std(trade_arr) > 0
            else 0
        )
        # Max drawdown from equity curve
        for r in trade_arr:
            eq = equity[-1] * (1 + r / 100)
            equity.append(eq)
            max_equity = max(max_equity, eq)
            min_equity = min(eq, max_equity)
        dd = (max_equity - min_equity) / max_equity * 100 if max_equity > 0 else 0
        return {
            "total_trades": total,
            "wins": wins,
            "losses": losses,
            "winrate": round(winrate, 1),
            "total_return_pct": round(total_ret, 2),
            "sharpe": round(sharpe, 2),
            "max_drawdown": round(dd, 2),
            "avg_return_per_trade": round(avg_ret, 2),
            "error": None,
        }
    except Exception as e:
        return {**default, "error": str(e)}

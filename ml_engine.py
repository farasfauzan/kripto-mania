"""
ML Ensemble Engine — Aggressive Scalper Mode v3
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
from sklearn.feature_selection import SelectKBest, mutual_info_classif

ML_AVAILABLE = True

# ── Logger ──
logger = None


def _ensure_logger():
    global logger
    if logger is None:
        try:
            from core.applog import get_logger

            logger = get_logger("ml_engine")
        except ImportError:
            import logging

            logger = logging.getLogger("ml_engine")
            logger.setLevel(logging.INFO)
            logger.addHandler(logging.StreamHandler())


_ensure_logger()
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
    prob_threshold_scalp: float = float(os.environ.get("ML_PROB_THRESHOLD", "75.0"))
    # Adaptive threshold — auto turun/naik based on volatility + streak
    adaptive_threshold_enabled: bool = True
    adaptive_threshold_min: float = float(os.environ.get("ML_ADAPTIVE_MIN", "55.0"))
    adaptive_threshold_base: float = float(os.environ.get("ML_ADAPTIVE_BASE", "75.0"))

    adaptive_threshold_factor_loss: float = 5.0  # naik 5% tiap consecutive loss
    adaptive_threshold_factor_win: float = -2.5  # turun 2.5% tiap win streak
    adaptive_threshold_vola_min: float = 50.0  # minimal threshold saat vola rendah
    adaptive_win_streak_cap: int = 3  # maks win streak sebelum threshold turun
    adaptive_loss_streak_cap: int = 2  # loss streak sebelum threshold naik
    # Online learning
    online_learning_enabled: bool = True
    online_learning_interval_hours: int = 4
    online_learning_max_samples: int = 5000
    ensemble_voting: str = "soft"
    use_stacking: bool = True
    max_features: int = int(os.environ.get("ML_MAX_FEATURES", "40"))
    drift_warning_zscore: float = float(os.environ.get("ML_DRIFT_ZSCORE", "2.5"))
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

    # Volume spike — rasio volume n-candle vs avg 20 candle
    for p in [1, 3, 5]:
        vol_avg_p = vol.rolling(p).mean()
        features[f"vol_spike_{p}v20"] = vol_avg_p / vol_sma20.replace(0, np.nan)
        features[f"vol_spike_{p}v5"] = vol_avg_p / vol.rolling(5).mean().replace(
            0, np.nan
        )
    # Volume z-score (standar deviasi volume 20-candle)
    vol_std20 = vol.rolling(20).std()
    features["vol_z20"] = (vol - vol.rolling(20).mean()) / vol_std20.replace(0, np.nan)
    features["vol_z20"] = features["vol_z20"].clip(-3, 3)

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
    features = features.ffill().bfill().fillna(0)

    return features


def _select_top_features_by_mutual_info(
    X: pd.DataFrame, y: pd.Series, k: int
) -> pd.DataFrame:
    """Feature selection pakai mutual information, bukan variance doang."""
    if X.shape[1] <= k:
        return X
    try:
        selector = SelectKBest(score_func=mutual_info_classif, k=k)
        selector.fit(X, y)
        mask = selector.get_support()
        selected = X.loc[:, mask]
        return selected
    except Exception:
        # fallback variance-based
        var = X.var().sort_values(ascending=False)
        keep = var.head(k).index
        return X[keep]


def _prepare_features_with_target(
    candles: pd.DataFrame,
    horizon: int = 3,
    target_pct: float = 1.0,
) -> tuple[pd.DataFrame, pd.Series, pd.DataFrame]:
    if candles is None or len(candles) < 60:
        return pd.DataFrame(), pd.Series(dtype=int), pd.DataFrame()

    close = candles["close"].astype(float)
    high = candles["high"].astype(float) if "high" in candles else close
    low = candles["low"].astype(float) if "low" in candles else close
    X_all = engineer_features(candles)

    # Market regime detection: filter target by recent volatility
    # Kalo volatility rendah, target lebih kecil; kalo tinggi, target lebih besar
    vola_20 = close.pct_change(20).std() * 100 if len(close) > 20 else 0
    regime_factor = max(0.5, min(2.0, vola_20 / 3.0))  # normalize around 3% vola
    adjusted_target_pct = target_pct * regime_factor

    # Triple-barrier labeling: target=1 hanya kalau take-profit (TP) tersentuh
    # SEBELUM stop-loss (SL) dalam window horizon. Ini menghindari label "win"
    # palsu di mana harga jatuh kena stop dulu baru naik.
    tp_level = close * (1 + adjusted_target_pct / 100.0)
    sl_pct = adjusted_target_pct  # SL simetris terhadap TP (risk:reward ~1:1)
    sl_level = close * (1 - sl_pct / 100.0)

    n = len(close)
    high_vals = high.values
    low_vals = low.values
    tp_vals = tp_level.values
    sl_vals = sl_level.values
    labels = np.zeros(n, dtype=float)
    labels[:] = np.nan
    for i in range(n):
        end = min(i + horizon, n - 1)
        if end <= i:
            continue
        hit = 0
        for j in range(i + 1, end + 1):
            tp_hit = high_vals[j] >= tp_vals[i]
            sl_hit = low_vals[j] <= sl_vals[i]
            if tp_hit and sl_hit:
                # Dua-duanya kena di candle yang sama → konservatif: anggap SL duluan
                hit = 0
                break
            if tp_hit:
                hit = 1
                break
            if sl_hit:
                hit = 0
                break
        labels[i] = hit
    target = pd.Series(labels, index=close.index)
    # Buang baris paling akhir yang window-nya belum lengkap (future tidak diketahui)
    if horizon > 0:
        target.iloc[-horizon:] = np.nan
    target = target.dropna().astype(int)

    valid = X_all.dropna().index.intersection(target.dropna().index)
    X = X_all.loc[valid]
    y = target.loc[valid]

    X = X.loc[:, X.nunique() > 1]

    if X.shape[1] > CFG.max_features:
        X = _select_top_features_by_mutual_info(X, y, CFG.max_features)

    if X.shape[1] > 1:
        current_X = X_all.iloc[[-1]].fillna(0)
        common_cols = current_X.columns.intersection(X.columns)
        current_X = current_X[common_cols]
        for col in X.columns:
            if col not in current_X.columns:
                current_X[col] = 0.0
        current_X = current_X[X.columns]
    else:
        current_X = pd.DataFrame()

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


def _build_one_model(name: str, best_params: dict | None = None) -> Any:
    """Bangun satu instance model baru (fresh) berdasarkan nama.

    Dipakai untuk evaluasi holdout supaya estimator evaluasi terpisah dari
    estimator produksi (yang di-fit ulang pakai seluruh data).
    """
    seed = 42
    if name == "rf":
        return RandomForestClassifier(
            n_estimators=150,
            max_depth=8,
            min_samples_leaf=5,
            random_state=seed,
            class_weight="balanced",
            n_jobs=-1,
        )
    if name == "xgb" and XGB_AVAILABLE:
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
        return xgb.XGBClassifier(**xgb_params)
    if name == "lgb" and LGBM_AVAILABLE:
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
        return lgb.LGBMClassifier(**lgb_params)
    raise ValueError(f"Unknown or unavailable model: {name}")


def _build_base_models(best_params: dict | None = None) -> list[tuple[str, Any]]:
    models = [("rf", _build_one_model("rf", best_params))]
    if XGB_AVAILABLE:
        models.append(("xgb", _build_one_model("xgb", best_params)))
    if LGBM_AVAILABLE:
        models.append(("lgb", _build_one_model("lgb", best_params)))
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

    # Time-based holdout untuk metrik yang JUJUR (out-of-sample).
    # Sebelumnya metrik dihitung di data training sendiri → terlalu optimistis.
    # Holdout dipakai khusus untuk evaluasi; model final tetap di-fit pakai semua data.
    split_idx = int(len(X_scaled) * (1 - CFG.test_size_walk))
    has_holdout = (
        split_idx >= 30
        and (len(X_scaled) - split_idx) >= 15
        and len(np.unique(y.iloc[:split_idx])) >= 2
        and len(np.unique(y.iloc[split_idx:])) >= 2
    )

    base_models = _build_base_models(best_params)

    individual_metrics = {}
    trained_estimators = []
    for name, model in base_models:
        try:
            # 1) Evaluasi out-of-sample lewat holdout (kalau cukup data).
            if has_holdout:
                eval_model = _build_one_model(name, best_params)
                eval_model.fit(X_scaled.iloc[:split_idx], y.iloc[:split_idx])
                Xh = X_scaled.iloc[split_idx:]
                yh = y.iloc[split_idx:]
                pred = eval_model.predict(Xh)
                proba = (
                    eval_model.predict_proba(Xh)[:, 1]
                    if hasattr(eval_model, "predict_proba")
                    else None
                )
                acc = accuracy_score(yh, pred)
                f1 = f1_score(yh, pred, zero_division=0)
                auc = roc_auc_score(yh, proba) if proba is not None else 0.0
                metric_kind = "holdout"
            else:
                # Data terlalu sedikit untuk holdout → tandai metrik in-sample.
                model_tmp = _build_one_model(name, best_params)
                model_tmp.fit(X_scaled, y)
                pred = model_tmp.predict(X_scaled)
                proba = (
                    model_tmp.predict_proba(X_scaled)[:, 1]
                    if hasattr(model_tmp, "predict_proba")
                    else None
                )
                acc = accuracy_score(y, pred)
                f1 = f1_score(y, pred, zero_division=0)
                auc = roc_auc_score(y, proba) if proba is not None else 0.0
                metric_kind = "in_sample"

            # 2) Fit model final pakai SEMUA data untuk produksi.
            model.fit(X_scaled, y)
            individual_metrics[name] = {
                "accuracy": round(acc, 4),
                "f1": round(f1, 4),
                "roc_auc": round(auc, 4),
                "metric_kind": metric_kind,
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
# 6. ADAPTIVE THRESHOLD
# ═════════════════════════════════════════════════════════════════════════════

_ADAPTIVE_STATE = {"consecutive_wins": 0, "consecutive_losses": 0}
_THRESHOLD_STATE_PATH = os.path.join(MODEL_DIR, "threshold_state.json")


def _save_adaptive_state():
    try:
        with open(_THRESHOLD_STATE_PATH, "w") as f:
            json.dump(_ADAPTIVE_STATE, f)
    except Exception:
        pass


def _load_adaptive_state():
    global _ADAPTIVE_STATE
    if os.path.exists(_THRESHOLD_STATE_PATH):
        try:
            with open(_THRESHOLD_STATE_PATH) as f:
                _ADAPTIVE_STATE.update(json.load(f))
        except Exception:
            pass


def _update_adaptive_streak(was_win: bool):
    if was_win:
        _ADAPTIVE_STATE["consecutive_wins"] += 1
        _ADAPTIVE_STATE["consecutive_losses"] = 0
    else:
        _ADAPTIVE_STATE["consecutive_losses"] += 1
        _ADAPTIVE_STATE["consecutive_wins"] = 0
    _save_adaptive_state()


def get_adaptive_threshold(candles: pd.DataFrame | None = None) -> float:
    if not CFG.adaptive_threshold_enabled:
        return CFG.prob_threshold_scalp

    _load_adaptive_state()
    wins = _ADAPTIVE_STATE.get("consecutive_wins", 0)
    losses = _ADAPTIVE_STATE.get("consecutive_losses", 0)

    base = CFG.adaptive_threshold_base
    win_adj = min(wins, CFG.adaptive_win_streak_cap) * CFG.adaptive_threshold_factor_win
    loss_adj = (
        min(losses, CFG.adaptive_loss_streak_cap) * CFG.adaptive_threshold_factor_loss
    )

    # Volatility adj — kalo volatilitas tinggi, threshold turun
    vola_adj = 0.0
    if candles is not None and len(candles) > 20:
        try:
            close = candles["close"].astype(float)
            vola_20 = close.pct_change(20).std() * 100
            vola_factor = max(CFG.adaptive_threshold_vola_min, min(100.0, vola_20 * 5))
            vola_adj = (50.0 - vola_factor) * 0.3
        except Exception:
            pass

    threshold = base + win_adj + loss_adj + vola_adj
    return max(CFG.adaptive_threshold_min, min(95.0, threshold))


# ═════════════════════════════════════════════════════════════════════════════
# 7. ONLINE LEARNING
# ═════════════════════════════════════════════════════════════════════════════

_ONLINE_BUFFER = {"X": [], "y": [], "last_retrain": 0}
_ONLINE_BUFFER_PATH = os.path.join(MODEL_DIR, "online_buffer.json")


def _save_online_buffer():
    try:
        data = {
            "X": _ONLINE_BUFFER["X"],
            "y": _ONLINE_BUFFER["y"],
            "last_retrain": _ONLINE_BUFFER["last_retrain"],
        }
        with open(_ONLINE_BUFFER_PATH, "w") as f:
            json.dump(data, f, default=str)
    except Exception:
        pass


def _load_online_buffer():
    if os.path.exists(_ONLINE_BUFFER_PATH):
        try:
            with open(_ONLINE_BUFFER_PATH) as f:
                data = json.load(f)
            _ONLINE_BUFFER["X"] = data.get("X", [])
            _ONLINE_BUFFER["y"] = data.get("y", [])
            _ONLINE_BUFFER["last_retrain"] = data.get("last_retrain", 0)
        except Exception:
            pass


def record_online_feedback(symbol: str, features: dict, was_win: bool):
    if not CFG.online_learning_enabled:
        return
    _load_online_buffer()
    _ONLINE_BUFFER["X"].append({"symbol": symbol, **features})
    _ONLINE_BUFFER["y"].append(1 if was_win else 0)
    if len(_ONLINE_BUFFER["y"]) > CFG.online_learning_max_samples:
        _ONLINE_BUFFER["X"] = _ONLINE_BUFFER["X"][-CFG.online_learning_max_samples :]
        _ONLINE_BUFFER["y"] = _ONLINE_BUFFER["y"][-CFG.online_learning_max_samples :]
    _save_online_buffer()

    _update_adaptive_streak(was_win)
    _check_online_retrain()


def _check_online_retrain():
    now = datetime.now(WIB).timestamp()
    elapsed = now - _ONLINE_BUFFER["last_retrain"]
    if elapsed < CFG.online_learning_interval_hours * 3600:
        return
    if len(_ONLINE_BUFFER["y"]) < CFG.min_train_samples:
        return
    try:
        X_buf = _ONLINE_BUFFER["X"]
        y_buf = np.array(_ONLINE_BUFFER["y"])
        if len(np.unique(y_buf)) < 2 or len(X_buf) < 50:
            return
        # Buang kolom non-fitur (mis. 'symbol') dan ambil hanya numerik.
        # JANGAN di-scale di sini — train_ensemble sudah men-scale sendiri
        # pakai RobustScaler. Scaling dobel bikin distribusi fitur rusak.
        raw = pd.DataFrame(X_buf)
        if "symbol" in raw.columns:
            raw = raw.drop(columns=["symbol"])
        df = raw.select_dtypes(include=[np.number]).fillna(0.0)
        # Pakai hanya fitur yang dikenal model saat ini supaya ruang fitur konsisten.
        if os.path.exists(FEATURE_META_PATH):
            try:
                with open(FEATURE_META_PATH) as f:
                    known = json.load(f).get("feature_names", [])
                common = [c for c in known if c in df.columns]
                if len(common) >= 5:
                    df = df[common]
            except Exception:
                pass
        if df.shape[1] < 5:
            return
        result = train_ensemble(df, pd.Series(y_buf))

        if result["success"]:
            _ONLINE_BUFFER["last_retrain"] = now
            _ONLINE_BUFFER["X"] = []
            _ONLINE_BUFFER["y"] = []
            _save_online_buffer()
            logger.info(
                f"Online retrain done v{result['version']} — {result['n_samples']} samples"
            )
    except Exception as e:
        logger.error(f"Online retrain failed: {e}")


# ═════════════════════════════════════════════════════════════════════════════
# 8. PREDICTION
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
        ref_mean = np.array(meta["scaler_center"], dtype=float)
        ref_std = np.array(meta["scaler_scale"], dtype=float)
        feat_names = meta.get("feature_names", [])
        if len(ref_mean) == 0 or len(ref_std) == 0 or not feat_names:
            return 0.0
        # Bandingkan PER FITUR berdasarkan nama (bukan posisi flatten yang bisa
        # tidak sinkron). ref_mean/ref_std diurutkan sesuai feat_names.
        z_scores = []
        for idx, fname in enumerate(feat_names):
            if idx >= len(ref_mean) or idx >= len(ref_std):
                break
            if fname not in current_X.columns:
                continue
            cur = float(current_X[fname].iloc[0])
            z = abs((cur - ref_mean[idx]) / (ref_std[idx] + 1e-8))
            z_scores.append(z)
        if len(z_scores) < 2:
            return 0.0
        return float(np.max(z_scores))

    except Exception:
        return 0.0


def detect_volume_spike(candles: pd.DataFrame) -> dict | None:
    """
    Deteksi eksplisit volume spike independen dari model.
    Return signal dict kalo spike terdeteksi, None kalo ga.
    """
    if candles is None or len(candles) < 25:
        return None
    try:
        vol = candles["volume"].astype(float)
        close = candles["close"].astype(float)

        vol_ma20 = vol.tail(20).mean()
        vol_ma5 = vol.tail(5).mean()
        last_vol = vol.iloc[-1]
        prev_vol = vol.iloc[-2] if len(vol) > 1 else last_vol

        if vol_ma20 <= 0:
            return None

        vr1 = last_vol / vol_ma20  # spike rasio vs avg 20
        vr3 = vol.tail(3).mean() / vol_ma20
        vol_z = (last_vol - vol_ma20) / (vol.tail(20).std() + 1e-8)

        # Harga
        ret1 = close.pct_change(1).iloc[-1] * 100
        ret3 = close.pct_change(3).iloc[-1] * 100
        ret5 = close.pct_change(5).iloc[-1] * 100 if len(close) > 5 else 0

        # Syarat spike: volume naik >= 2.5x avg 20 + z-score >= 1.5
        # Harga harus naik untuk sinyal buy (spike + harga turun = distribusi/panic)
        is_spike = vr1 >= 2.5 and vol_z >= 1.5
        price_ok = ret1 > -1.0 and ret3 > -1.5

        if is_spike and price_ok:
            base_prob = min(
                85.0, 50.0 + (vr1 - 2.5) * 8 + max(0, ret1) * 2 + max(0, ret3) * 1.5
            )
            prob_up = min(92, max(60, base_prob))
            strength = "KERAS" if vr1 >= 5.0 or vol_z >= 3.0 else "SEDANG"
            return {
                "prob_up_pct": round(prob_up, 1),
                "is_scalp_valid": True,
                "confidence": strength,
                "ensemble_detail": {
                    "volume_spike_vr1": round(vr1, 2),
                    "volume_spike_vr3": round(vr3, 2),
                    "volume_spike_z": round(vol_z, 2),
                    "ret1": round(ret1, 2),
                    "ret3": round(ret3, 2),
                },
                "drift_warning": None,
            }

        # Volume spike tp harga turun — mungkin distribusi / panic sell
        if is_spike and not price_ok:
            return {
                "prob_up_pct": max(5, 30 + (vr1 - 2.5) * -3),
                "is_scalp_valid": False,
                "confidence": "LEMAH",
                "ensemble_detail": {
                    "volume_spike_vr1": round(vr1, 2),
                    "volume_spike_z": round(vol_z, 2),
                    "note": "volume spike with price drop — distribution/panic",
                },
                "drift_warning": None,
            }

        return None
    except Exception:
        return None


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
        "entry_features": {},
    }

    X, y, current_X = _prepare_features_with_target(candles, horizon=3, target_pct=1.0)
    if X.empty or current_X.empty or len(X) < 30:
        return _fallback_prediction(candles)

    # 1. Cek volume spike deteksi ekplisit terlebih dahulu
    spike_sig = detect_volume_spike(candles)
    if spike_sig is not None and spike_sig.get("is_scalp_valid"):
        features_dict = {}
        try:
            for k, v in current_X.iloc[0].to_dict().items():
                if isinstance(v, (float, np.floating)):
                    features_dict[k] = float(v)
                elif isinstance(v, (int, np.integer)):
                    features_dict[k] = int(v)
                else:
                    features_dict[k] = v
        except Exception:
            pass
        spike_sig["entry_features"] = features_dict
        logger.info(
            f"Volume spike buy signal detected: returning spike signal (prob: {spike_sig['prob_up_pct']}%)"
        )
        return spike_sig

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

        if scaler is not None:
            try:
                current_scaled = scaler.transform(current_X)
                current_scaled = pd.DataFrame(
                    current_scaled, columns=feature_names, index=current_X.index
                )
            except Exception:
                current_scaled = current_X.values.reshape(1, -1)
        else:
            current_scaled = current_X.values.reshape(1, -1)

        probas = {}
        for name, model in ensemble.get("models", []):
            try:
                p = model.predict_proba(current_scaled)[:, 1]
                probas[name] = float(p[0])
            except Exception:
                probas[name] = 0.0

        voting_proba = None
        if voting is not None:
            try:
                voting_proba = float(voting.predict_proba(current_scaled)[:, 1][0])
            except Exception:
                voting_proba = None

        stacking_proba = None
        if stacking is not None:
            try:
                stacking_proba = float(stacking.predict_proba(current_scaled)[:, 1][0])
            except Exception:
                stacking_proba = None

        # Pilih sumber probabilitas dengan urutan prioritas yang eksplisit.
        # Gunakan `is not None` (bukan `or`) supaya nilai valid 0.0 tidak di-skip.
        if voting_proba is not None:
            final_proba = voting_proba
        elif stacking_proba is not None:
            final_proba = stacking_proba
        elif probas:
            final_proba = float(np.mean(list(probas.values())))
        else:
            final_proba = 0.5  # skala 0-1, konsisten dengan cabang lain
        prob_up = round(final_proba * 100, 1)

        drift_z = _detect_feature_drift(current_X, ensemble)

        detail = {
            "models": {k: round(v * 100, 1) for k, v in probas.items()},
            "voting": round(voting_proba * 100, 1) if voting_proba else None,
            "stacking": round(stacking_proba * 100, 1) if stacking_proba else None,
            "drift_z": round(drift_z, 2),
            "n_features": len(feature_names),
            "walk_f1": ensemble.get("walk_forward_metrics", {}).get("f1", None),
        }

        # Dapatkan threshold adaptif
        threshold = get_adaptive_threshold(candles)
        is_valid = prob_up >= threshold
        if drift_z > CFG.drift_warning_zscore:
            is_valid = False

        confidence = (
            "KERAS"
            if prob_up >= 85
            else ("SEDANG" if prob_up >= threshold else "LEMAH")
        )
        drift_warn = (
            f"DRIFT Z={drift_z:.1f}" if drift_z > CFG.drift_warning_zscore else None
        )

        # Siapkan entry features dict
        features_dict = {}
        try:
            for k, v in current_X.iloc[0].to_dict().items():
                if isinstance(v, (float, np.floating)):
                    features_dict[k] = float(v)
                elif isinstance(v, (int, np.integer)):
                    features_dict[k] = int(v)
                else:
                    features_dict[k] = v
        except Exception:
            pass

        return {
            "prob_up_pct": prob_up,
            "is_scalp_valid": is_valid,
            "confidence": confidence,
            "ensemble_detail": detail,
            "drift_warning": drift_warn,
            "entry_features": features_dict,
        }
    except Exception as e:
        logger.error(f"predict_aggressive_scalp failed, using fallback: {e}")
        return _fallback_prediction(candles)

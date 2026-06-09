"""
ML Engine - Aggressive Scalper Mode
===================================
Modul ini menggantikan/melengkapi K-Nearest Neighbors statis dengan XGBoost
untuk mendapatkan sinyal 'Quick In, Quick Out' (Scalping) dengan akurasi pro-trader.

Sistem akan memprediksi probabilitas koin naik sekian persen dalam timeframe sangat pendek.
"""

from __future__ import annotations
import os
import pickle
import numpy as np
import pandas as pd

try:
    import xgboost as xgb
    from sklearn.metrics import accuracy_score
    ML_AVAILABLE = True
except ImportError:
    ML_AVAILABLE = False

MODEL_PATH = "aggressive_scalper_model.pkl"

def _prepare_features(candles: pd.DataFrame, horizon: int = 2, target_pct: float = 0.8) -> tuple[pd.DataFrame, pd.Series, pd.DataFrame]:
    """Menyiapkan fitur untuk training XGBoost.
    Fitur berfokus pada momentum jangka pendek."""
    close = candles["close"].astype(float)
    high = candles["high"].astype(float)
    low = candles["low"].astype(float)
    volume = candles["volume"].astype(float)
    
    # Hitung returns
    ret1 = close.pct_change(1) * 100
    ret3 = close.pct_change(3) * 100
    
    # RSI (14)
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rsi = 100 - (100 / (1 + gain / loss.replace(0, np.nan)))
    
    # Volatility & Volume
    vol12 = ret1.rolling(12).std()
    vr = volume / volume.rolling(12).mean().replace(0, np.nan)
    
    # Bollinger Bands spread
    ma20 = close.rolling(20).mean()
    std20 = close.rolling(20).std()
    bb_upper = ma20 + (std20 * 2)
    bb_lower = ma20 - (std20 * 2)
    bb_width = (bb_upper - bb_lower) / ma20 * 100
    
    # Features dataframe
    feat = pd.DataFrame({
        "ret1": ret1,
        "ret3": ret3,
        "rsi": rsi,
        "vol12": vol12,
        "vr": vr,
        "bb_width": bb_width
    })
    
    # Target: 1 jika max_high dalam `horizon` candle ke depan > target_pct
    future_high = high.rolling(horizon).max().shift(-horizon)
    target = ((future_high - close) / close * 100) > target_pct
    
    # Drop NAs
    valid_idx = feat.dropna().index.intersection(target.dropna().index)
    
    X = feat.loc[valid_idx]
    y = target.loc[valid_idx].astype(int)
    
    # Data saat ini (candle terakhir) untuk prediksi
    current_X = feat.iloc[[-1]].fillna(0)
    
    return X, y, current_X

def train_or_update_model(candles: pd.DataFrame):
    """Melatih ulang model XGBoost jika data cukup."""
    if not ML_AVAILABLE or candles is None or len(candles) < 100:
        return False
        
    # Untuk scalping agresif, kita cari momentum 0.8% - 1.5% dalam 1-3 candle
    X, y, _ = _prepare_features(candles, horizon=3, target_pct=1.0)
    
    if len(X) < 50:
        return False
        
    model = xgb.XGBClassifier(
        n_estimators=100,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.8,
        random_state=42,
        eval_metric='logloss'
    )
    
    model.fit(X, y)
    
    # Simpan model
    with open(MODEL_PATH, "wb") as f:
        pickle.dump(model, f)
        
    return True

def predict_aggressive_scalp(candles: pd.DataFrame) -> dict:
    """Prediksi probabilitas scalp jangka pendek menggunakan XGBoost."""
    default = {
        "prob_up_pct": 50.0,
        "is_scalp_valid": False,
        "confidence": "NO DATA"
    }
    
    if not ML_AVAILABLE or candles is None or len(candles) < 30:
        return default
        
    try:
        X, y, current_X = _prepare_features(candles, horizon=3, target_pct=1.0)
        
        # Load model, atau latih jika belum ada
        if not os.path.exists(MODEL_PATH):
            success = train_or_update_model(candles)
            if not success:
                return default
                
        with open(MODEL_PATH, "rb") as f:
            model = pickle.load(f)
            
        # Prediksi probabilitas kelas 1 (Naik target tercapai)
        prob = model.predict_proba(current_X)[0][1] * 100
        
        is_valid = prob > 70.0
        
        if prob > 85.0:
            conf = "SANGAT TINGGI"
        elif prob > 70.0:
            conf = "TINGGI"
        elif prob > 50.0:
            conf = "MODERAT"
        else:
            conf = "LEMAH"
            
        return {
            "prob_up_pct": round(prob, 2),
            "is_scalp_valid": is_valid,
            "confidence": conf
        }
    except Exception as e:
        print(f"Aggressive ML Error: {e}")
        return default

"""
Smart Engine
============
Lapisan tambahan yang membungkus 3 library populer dengan **graceful import** —
kalau library tidak terinstall, web tetap jalan dengan fallback default aman.

Modul:
- `pandas_ta` (130+ indikator): tambah Ichimoku, Squeeze Momentum, OBV, MFI, KDJ
  ke confluence layer.
- `tradingview_ta`: second-opinion rating dari TradingView (free, tanpa API key).
- `quantstats`: generate metrik performance (Sharpe, max DD, equity curve)
  dari journal signal.

Semua fungsi defensif. Cek `is_available()` sebelum panggil fungsi turunan
yang spesifik library, atau langsung pakai high-level wrapper di sini.
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any

import pandas as pd

# =============================================================================
# GRACEFUL IMPORTS
# =============================================================================
try:
    import pandas_ta as pta  # type: ignore
    PTA_AVAILABLE = True
except Exception:  # pragma: no cover
    try:
        import pandas_ta_classic as pta  # type: ignore
        PTA_AVAILABLE = True
    except Exception:
        pta = None  # type: ignore
        PTA_AVAILABLE = False

try:
    from tradingview_ta import TA_Handler, Interval  # type: ignore
    TV_AVAILABLE = True
except Exception:  # pragma: no cover
    TA_Handler = None  # type: ignore
    Interval = None  # type: ignore
    TV_AVAILABLE = False

try:
    import quantstats as qs  # type: ignore
    QS_AVAILABLE = True
except Exception:  # pragma: no cover
    qs = None  # type: ignore
    QS_AVAILABLE = False


def is_available() -> dict:
    """Diagnostic — tahu library mana yang aktif."""
    return {
        "pandas_ta": PTA_AVAILABLE,
        "tradingview_ta": TV_AVAILABLE,
        "quantstats": QS_AVAILABLE,
    }


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        v = float(value)
        if math.isnan(v) or math.isinf(v):
            return default
        return v
    except (TypeError, ValueError):
        return default


# =============================================================================
# PANDAS-TA INDICATORS
# =============================================================================
def compute_ichimoku(candles: pd.DataFrame) -> dict:
    """Ichimoku cloud bias.

    Returns:
        {ichimoku_signal, cloud_bias, kumo_thickness}
    """
    default = {"ichimoku_signal": "NO DATA", "cloud_bias": "neutral", "kumo_thickness_pct": 0.0}
    if not PTA_AVAILABLE or candles is None or candles.empty or len(candles) < 60:
        return default
    try:
        high = candles["high"].astype(float)
        low = candles["low"].astype(float)
        close = candles["close"].astype(float)
        ichi = pta.ichimoku(high, low, close)
        if not isinstance(ichi, tuple) or len(ichi) < 1:
            return default
        df_ichi = ichi[0]
        # kolom utama: ISA_9 (Senkou A), ISB_26 (Senkou B), ITS_9 (Tenkan), IKS_26 (Kijun)
        col_a = next((c for c in df_ichi.columns if c.startswith("ISA_")), None)
        col_b = next((c for c in df_ichi.columns if c.startswith("ISB_")), None)
        col_t = next((c for c in df_ichi.columns if c.startswith("ITS_")), None)
        col_k = next((c for c in df_ichi.columns if c.startswith("IKS_")), None)
        if not all((col_a, col_b, col_t, col_k)):
            return default
        a_now = _safe_float(df_ichi[col_a].iloc[-1])
        b_now = _safe_float(df_ichi[col_b].iloc[-1])
        t_now = _safe_float(df_ichi[col_t].iloc[-1])
        k_now = _safe_float(df_ichi[col_k].iloc[-1])
        price = float(close.iloc[-1])
        if a_now <= 0 or b_now <= 0 or price <= 0:
            return default
        cloud_top = max(a_now, b_now)
        cloud_bottom = min(a_now, b_now)
        thickness_pct = (cloud_top - cloud_bottom) / price * 100
        if price > cloud_top and a_now > b_now and t_now > k_now:
            sig = "STRONG BULL"
            bias = "bullish"
        elif price > cloud_top:
            sig = "ABOVE CLOUD"
            bias = "bullish"
        elif price < cloud_bottom and a_now < b_now and t_now < k_now:
            sig = "STRONG BEAR"
            bias = "bearish"
        elif price < cloud_bottom:
            sig = "BELOW CLOUD"
            bias = "bearish"
        else:
            sig = "INSIDE CLOUD"
            bias = "neutral"
        return {
            "ichimoku_signal": sig,
            "cloud_bias": bias,
            "kumo_thickness_pct": round(thickness_pct, 2),
        }
    except Exception:
        return default


def compute_squeeze_momentum(candles: pd.DataFrame) -> dict:
    """LazyBear Squeeze Momentum: cari volatility compression sebelum breakout."""
    default = {"squeeze": "NO DATA", "squeeze_momentum": 0.0, "breakout_imminent": False}
    if not PTA_AVAILABLE or candles is None or candles.empty or len(candles) < 30:
        return default
    try:
        high = candles["high"].astype(float)
        low = candles["low"].astype(float)
        close = candles["close"].astype(float)
        sqz = pta.squeeze(high, low, close, lazybear=True)
        if sqz is None or sqz.empty:
            return default
        # kolom: SQZ_ON, SQZ_OFF, SQZ_NO, SQZ_20_2.0_20_1.5_LB (momentum)
        on_col = next((c for c in sqz.columns if "ON" in c.upper()), None)
        off_col = next((c for c in sqz.columns if "OFF" in c.upper()), None)
        mom_col = next((c for c in sqz.columns if "LB" in c.upper() or c.startswith("SQZ_") and c.endswith("LB")), None)
        if mom_col is None:
            mom_col = sqz.columns[-1]
        on_now = bool(sqz[on_col].iloc[-1]) if on_col else False
        off_now = bool(sqz[off_col].iloc[-1]) if off_col else False
        mom_now = _safe_float(sqz[mom_col].iloc[-1])
        if on_now:
            label = "SQUEEZED"
        elif off_now:
            label = "RELEASED"
        else:
            label = "NORMAL"
        # breakout imminent: squeeze on selama beberapa bar lalu momentum mulai naik
        last_n_on = sqz[on_col].tail(5).sum() if on_col else 0
        breakout = last_n_on >= 3 and mom_now > 0
        return {
            "squeeze": label,
            "squeeze_momentum": round(mom_now, 4),
            "breakout_imminent": bool(breakout),
        }
    except Exception:
        return default


def compute_obv_signal(candles: pd.DataFrame) -> dict:
    """On-Balance Volume divergence dengan harga."""
    default = {"obv_signal": "NO DATA", "obv_trend": "neutral"}
    if not PTA_AVAILABLE or candles is None or candles.empty or len(candles) < 30:
        return default
    try:
        close = candles["close"].astype(float)
        vol = candles["volume"].astype(float)
        obv = pta.obv(close, vol)
        if obv is None or obv.empty:
            return default
        recent = obv.tail(20)
        price_recent = close.tail(20)
        obv_slope = (recent.iloc[-1] - recent.iloc[0]) / max(abs(recent.iloc[0]), 1)
        price_slope = (price_recent.iloc[-1] - price_recent.iloc[0]) / max(price_recent.iloc[0], 1)
        if obv_slope > 0.05 and price_slope < -0.01:
            sig = "BULL DIVERGENCE"
            trend = "bullish"
        elif obv_slope < -0.05 and price_slope > 0.01:
            sig = "BEAR DIVERGENCE"
            trend = "bearish"
        elif obv_slope > 0.02 and price_slope > 0:
            sig = "CONFIRMING UP"
            trend = "bullish"
        elif obv_slope < -0.02 and price_slope < 0:
            sig = "CONFIRMING DOWN"
            trend = "bearish"
        else:
            sig = "FLAT"
            trend = "neutral"
        return {"obv_signal": sig, "obv_trend": trend}
    except Exception:
        return default


def compute_mfi(candles: pd.DataFrame, length: int = 14) -> dict:
    """Money Flow Index — RSI versi volume-aware."""
    default = {"mfi": 50.0, "mfi_signal": "NEUTRAL"}
    if not PTA_AVAILABLE or candles is None or candles.empty or len(candles) < length + 5:
        return default
    try:
        high = candles["high"].astype(float)
        low = candles["low"].astype(float)
        close = candles["close"].astype(float)
        vol = candles["volume"].astype(float)
        mfi = pta.mfi(high, low, close, vol, length=length)
        if mfi is None or mfi.empty:
            return default
        v = _safe_float(mfi.iloc[-1], 50)
        if v >= 80:
            sig = "OVERBOUGHT"
        elif v >= 65:
            sig = "STRONG"
        elif v <= 20:
            sig = "OVERSOLD"
        elif v <= 35:
            sig = "WEAK"
        else:
            sig = "NEUTRAL"
        return {"mfi": round(v, 1), "mfi_signal": sig}
    except Exception:
        return default


def build_smart_indicators_bundle(candles: pd.DataFrame) -> dict:
    """Bundle semua pandas-ta indikator + agregat skor adjustment."""
    ichi = compute_ichimoku(candles)
    sqz = compute_squeeze_momentum(candles)
    obv = compute_obv_signal(candles)
    mfi = compute_mfi(candles)

    smart_adjust = 0
    notes: list[str] = []

    # Ichimoku
    if ichi["ichimoku_signal"] == "STRONG BULL":
        smart_adjust += 6
        notes.append("Ichimoku strong bull (+6)")
    elif ichi["ichimoku_signal"] == "ABOVE CLOUD":
        smart_adjust += 3
        notes.append("Di atas Kumo (+3)")
    elif ichi["ichimoku_signal"] == "STRONG BEAR":
        smart_adjust -= 7
        notes.append("Ichimoku strong bear (-7)")
    elif ichi["ichimoku_signal"] == "BELOW CLOUD":
        smart_adjust -= 4
        notes.append("Di bawah Kumo (-4)")

    # Squeeze (compression sebelum breakout)
    if sqz["breakout_imminent"]:
        smart_adjust += 4
        notes.append("Squeeze breakout (+4)")
    elif sqz["squeeze"] == "SQUEEZED" and sqz["squeeze_momentum"] > 0:
        smart_adjust += 2
        notes.append("Squeeze on, momentum + (+2)")

    # OBV divergence
    if obv["obv_signal"] == "BULL DIVERGENCE":
        smart_adjust += 5
        notes.append("OBV bull divergence (+5)")
    elif obv["obv_signal"] == "BEAR DIVERGENCE":
        smart_adjust -= 6
        notes.append("OBV bear divergence (-6)")
    elif obv["obv_signal"] == "CONFIRMING UP":
        smart_adjust += 1

    # MFI
    if mfi["mfi_signal"] == "OVERSOLD":
        smart_adjust += 3
        notes.append(f"MFI oversold {mfi['mfi']:.0f} (+3)")
    elif mfi["mfi_signal"] == "OVERBOUGHT":
        smart_adjust -= 4
        notes.append(f"MFI overbought {mfi['mfi']:.0f} (-4)")
    elif mfi["mfi_signal"] == "STRONG":
        smart_adjust += 1

    # Cap rentang adjustment
    smart_adjust = max(-15, min(12, smart_adjust))

    return {
        "available": PTA_AVAILABLE,
        "ichimoku": ichi,
        "squeeze": sqz,
        "obv": obv,
        "mfi": mfi,
        "smart_adjustment": smart_adjust,
        "smart_notes": notes[:4],
    }


# =============================================================================
# TRADINGVIEW SECOND-OPINION
# =============================================================================
# Tradingview pakai exchange code; di Indodax kebanyakan coin tradable di Binance,
# jadi default exchange = BINANCE dengan pair USDT.
def fetch_tradingview_rating(symbol: str, exchange: str = "BINANCE",
                              quote: str = "USDT", interval: str = "4h") -> dict:
    """Pull konsensus rating dari TradingView. Free, tanpa API key.

    Returns:
        {tv_recommendation, tv_buy, tv_sell, tv_neutral, tv_oscillators, tv_moving_averages}
    """
    default = {
        "tv_available": False,
        "tv_recommendation": "NO DATA",
        "tv_buy": 0,
        "tv_sell": 0,
        "tv_neutral": 0,
        "tv_oscillators": "NO DATA",
        "tv_moving_averages": "NO DATA",
    }
    if not TV_AVAILABLE or not symbol:
        return default
    interval_map = {
        "1m": Interval.INTERVAL_1_MINUTE,
        "5m": Interval.INTERVAL_5_MINUTES,
        "15m": Interval.INTERVAL_15_MINUTES,
        "1h": Interval.INTERVAL_1_HOUR,
        "2h": Interval.INTERVAL_2_HOURS,
        "4h": Interval.INTERVAL_4_HOURS,
        "1d": Interval.INTERVAL_1_DAY,
        "1w": Interval.INTERVAL_1_WEEK,
    }
    iv = interval_map.get(interval, Interval.INTERVAL_4_HOURS)
    try:
        handler = TA_Handler(
            symbol=f"{symbol.upper()}{quote.upper()}",
            screener="crypto",
            exchange=exchange,
            interval=iv,
        )
        analysis = handler.get_analysis()
        if not analysis:
            return default
        summary = analysis.summary or {}
        osc = analysis.oscillators or {}
        ma = analysis.moving_averages or {}
        rec = summary.get("RECOMMENDATION", "NO DATA")
        return {
            "tv_available": True,
            "tv_recommendation": rec,
            "tv_buy": int(summary.get("BUY", 0) or 0),
            "tv_sell": int(summary.get("SELL", 0) or 0),
            "tv_neutral": int(summary.get("NEUTRAL", 0) or 0),
            "tv_oscillators": osc.get("RECOMMENDATION", "NO DATA"),
            "tv_moving_averages": ma.get("RECOMMENDATION", "NO DATA"),
        }
    except Exception:
        return default


def tradingview_score_adjustment(tv_data: dict) -> tuple[int, str]:
    """Konversi rekomendasi TV jadi score adjustment.

    Returns:
        (adjustment, note)
    """
    if not tv_data or not tv_data.get("tv_available"):
        return 0, ""
    rec = (tv_data.get("tv_recommendation") or "").upper()
    buy = tv_data.get("tv_buy", 0)
    sell = tv_data.get("tv_sell", 0)
    if rec == "STRONG_BUY" and buy >= sell + 8:
        return 5, "TV strong buy (+5)"
    if rec in ("STRONG_BUY", "BUY"):
        return 3, "TV buy (+3)"
    if rec == "STRONG_SELL" and sell >= buy + 8:
        return -6, "TV strong sell (-6)"
    if rec in ("STRONG_SELL", "SELL"):
        return -3, "TV sell (-3)"
    return 0, ""


# =============================================================================
# QUANTSTATS PORTFOLIO METRICS DARI SIGNAL JOURNAL
# =============================================================================
def compute_journal_metrics(journal: dict) -> dict:
    """Hitung Sharpe, Sortino, max DD, win/loss ratio dari signal journal.

    Strategi: kita treat setiap closed signal sebagai 1 "trade return" yang
    dihitung dari `max_gain_pct` (kalau win) atau `max_drawdown_pct` (kalau loss).
    Hasilkan equity curve & metrik standar.
    """
    default = {
        "available": QS_AVAILABLE,
        "trades": 0,
        "winrate": None,
        "avg_return_pct": 0.0,
        "best_trade_pct": 0.0,
        "worst_trade_pct": 0.0,
        "sharpe": None,
        "sortino": None,
        "max_drawdown_pct": None,
        "equity_curve": [],
        "profit_factor": None,
    }
    signals = (journal or {}).get("signals", [])
    closed = [s for s in signals if s.get("status") in {"TARGET", "TP", "SL", "EXPIRED"}]
    if not closed:
        return default

    # Translate ke list of returns. Asumsi 1 unit modal per trade.
    returns_pct = []
    for s in sorted(closed, key=lambda x: x.get("opened_at") or ""):
        outcome = s.get("outcome")
        if outcome == "WIN":
            ret = _safe_float(s.get("max_gain_pct"), 0)
            if ret <= 0:
                ret = 1.5  # fallback minimal win
        else:
            ret = _safe_float(s.get("max_drawdown_pct"), 0)
            if ret >= 0:
                ret = -2.0
        returns_pct.append(ret)

    n = len(returns_pct)
    wins = [r for r in returns_pct if r > 0]
    losses = [r for r in returns_pct if r <= 0]
    winrate = round(len(wins) / n * 100, 1) if n else None
    avg = sum(returns_pct) / n if n else 0
    best = max(returns_pct) if returns_pct else 0
    worst = min(returns_pct) if returns_pct else 0

    # Equity curve sederhana, compounding 1 satuan modal
    equity = [1.0]
    for r in returns_pct:
        equity.append(equity[-1] * (1 + r / 100))
    equity_curve = [round(e, 4) for e in equity]

    # Max drawdown
    peak = equity[0]
    max_dd = 0
    for e in equity:
        peak = max(peak, e)
        dd = (e - peak) / peak * 100
        if dd < max_dd:
            max_dd = dd

    # Profit factor = total wins / |total losses|
    sum_wins = sum(wins)
    sum_losses = abs(sum(losses)) or 1
    profit_factor = round(sum_wins / sum_losses, 2) if losses else None

    # Sharpe/Sortino via quantstats kalau ada, kalau tidak hitung manual
    sharpe = sortino = None
    if returns_pct:
        try:
            ret_series = pd.Series([r / 100 for r in returns_pct])
            std = ret_series.std()
            if std and std > 0:
                # asumsi 1 sinyal = 1 day, annualisasi 252
                sharpe = round(float(ret_series.mean() / std * (252 ** 0.5)), 2)
            negative = ret_series[ret_series < 0]
            downside = negative.std()
            if downside and downside > 0:
                sortino = round(float(ret_series.mean() / downside * (252 ** 0.5)), 2)

            if QS_AVAILABLE:
                # quantstats butuh DatetimeIndex. Pakai opened_at sebagai timeline.
                try:
                    dates = pd.to_datetime([s.get("opened_at") for s in closed], errors="coerce")
                    if dates.notna().all():
                        ts = pd.Series(ret_series.values, index=dates).sort_index()
                        sh_q = qs.stats.sharpe(ts)
                        so_q = qs.stats.sortino(ts)
                        if pd.notna(sh_q):
                            sharpe = round(float(sh_q), 2)
                        if pd.notna(so_q):
                            sortino = round(float(so_q), 2)
                except Exception:
                    pass
        except Exception:
            pass

    return {
        "available": QS_AVAILABLE,
        "trades": n,
        "winrate": winrate,
        "avg_return_pct": round(avg, 2),
        "best_trade_pct": round(best, 2),
        "worst_trade_pct": round(worst, 2),
        "sharpe": sharpe,
        "sortino": sortino,
        "max_drawdown_pct": round(max_dd, 2),
        "equity_curve": equity_curve,
        "profit_factor": profit_factor,
    }

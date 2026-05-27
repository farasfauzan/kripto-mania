"""
Advanced Algorithms - 15 algoritma canggih pure pandas/numpy.
Defensive semua, kembalikan default aman jika data kurang.
"""

from __future__ import annotations
import math
from typing import Any
import numpy as np
import pandas as pd


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _safe_float(v: Any, d: float = 0.0) -> float:
    try:
        if v is None:
            return d
        f = float(v)
        return d if math.isnan(f) or math.isinf(f) else f
    except (TypeError, ValueError):
        return d


# -----------------------------------------------------------------------------
# 1. VOLUME PROFILE VISIBLE RANGE (VPVR)
# -----------------------------------------------------------------------------
def compute_volume_profile(candles: pd.DataFrame, num_bins: int = 20) -> dict:
    d = {"poc": None, "va_high": None, "va_low": None, "vai": 0.0,
         "hvn_count": 0, "lvn_count": 0, "profile_shape": "UNKNOWN"}
    if candles is None or candles.empty or len(candles) < 20:
        return d
    try:
        c, v, h, lo = candles["close"].astype(float), candles["volume"].astype(float), candles["high"].astype(float), candles["low"].astype(float)
        pr = h.max() - lo.min()
        if pr <= 0:
            return d
        bins = np.linspace(lo.min(), h.max(), num_bins + 1)
        bv, bc = [], []
        for i in range(num_bins):
            m = (c >= bins[i]) & (c < bins[i + 1])
            bv.append(v[m].sum())
            bc.append((bins[i] + bins[i + 1]) / 2)
        bv, bc = np.array(bv), np.array(bc)
        tv = bv.sum()
        if tv <= 0:
            return d
        si = np.argsort(bv)[::-1]
        poc = float(bc[si[0]])
        cum, va = 0, []
        for idx in si:
            cum += bv[idx]
            va.append(bc[idx])
            if cum >= tv * 0.70:
                break
        va = np.array(va)
        vah, val = float(va.max()), float(va.min())
        vai = ((vah - val) / (poc or 1)) * 100
        hvn = int((bv > np.percentile(bv, 70)).sum())
        lvn = int((bv < np.percentile(bv, 30)).sum())
        lh, rh = bv[:num_bins // 2].sum(), bv[num_bins // 2:].sum()
        shape = "LEFT-HEAVY (BULLISH)" if lh > rh * 1.5 else "RIGHT-HEAVY (BEARISH)" if rh > lh * 1.5 else "BALANCED"
        return {"poc": poc, "va_high": vah, "va_low": val, "vai": round(vai, 2),
                "hvn_count": hvn, "lvn_count": lvn, "profile_shape": shape}
    except Exception:
        return d


# -----------------------------------------------------------------------------
# 2. SUPPORT/RESISTANCE STRENGTH
# -----------------------------------------------------------------------------
def compute_sr_strength(candles: pd.DataFrame, tol: float = 1.5) -> dict:
    d = {"supports": [], "resistances": [], "strongest_sr": None}
    if candles is None or candles.empty or len(candles) < 30:
        return d
    try:
        c, h, lo, v = [candles[x].astype(float) for x in ("close", "high", "low", "volume")]
        price = float(c.iloc[-1])
        levels = []
        for i in range(2, len(candles) - 2):
            if lo.iloc[i] <= lo.iloc[i-1] and lo.iloc[i] <= lo.iloc[i+1] and lo.iloc[i] <= lo.iloc[i-2] and lo.iloc[i] <= lo.iloc[i+2]:
                levels.append({"price": lo.iloc[i], "type": "support", "idx": i})
            if h.iloc[i] >= h.iloc[i-1] and h.iloc[i] >= h.iloc[i+1] and h.iloc[i] >= h.iloc[i-2] and h.iloc[i] >= h.iloc[i+2]:
                levels.append({"price": h.iloc[i], "type": "resistance", "idx": i})
        clusters = []
        for lv in sorted(levels, key=lambda x: x["price"]):
            found = False
            for cl in clusters:
                if abs(lv["price"] - cl["price"]) / cl["price"] * 100 <= tol:
                    cl["touches"] += 1
                    cl["idx"].append(lv["idx"])
                    found = True
                    break
            if not found:
                clusters.append({"price": lv["price"], "type": lv["type"], "touches": 1, "idx": [lv["idx"]]})
        sup, res = [], []
        for cl in clusters:
            ts = min(cl["touches"] * 15, 40)
            vr = v[cl["idx"]].mean() / v.mean() if v.mean() > 0 else 1
            vs = min(vr * 20, 30)
            dist = abs(price - cl["price"]) / cl["price"] * 100
            ps = max(0, 30 - dist * 3)
            ls = len(candles) - 1 - max(cl["idx"])
            rs = max(0, 20 - ls * 2)
            st = ts + vs + ps + rs
            ld = {"price": round(cl["price"], 6), "strength": round(st, 1),
                  "touches": cl["touches"], "last_seen": ls, "vol_ratio": round(vr, 2)}
            (sup if cl["type"] == "support" else res).append(ld)
        sup.sort(key=lambda x: x["strength"], reverse=True)
        res.sort(key=lambda x: x["strength"], reverse=True)
        all_lv = sup + res
        return {"supports": sup[:5], "resistances": res[:5], "strongest_sr": all_lv[0] if all_lv else None}
    except Exception:
        return d


# -----------------------------------------------------------------------------
# 3. ENHANCED RSI DIVERGENCE
# -----------------------------------------------------------------------------
def detect_rsi_divergence(candles: pd.DataFrame, lb: int = 80) -> dict:
    d = {"divergence": "NONE", "strength": 0, "type": "NONE", "price_now": None, "rsi_now": None}
    if candles is None or candles.empty or len(candles) < max(40, lb):
        return d
    try:
        c, lo, h = [candles[x].astype(float) for x in ("close", "low", "high")]
        delta = c.diff()
        gain = delta.clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
        loss = (-delta.clip(upper=0)).ewm(alpha=1/14, adjust=False).mean()
        rsi = (100 - (100 / (1 + gain / loss.replace(0, np.nan)))).fillna(50)
        cw, lw, hw, rw = [x.tail(lb) for x in (c, lo, h, rsi)]
        n = len(cw)
        if n < 30:
            return d
        sl, sh = [], []
        for i in range(2, n - 2):
            if lw.iloc[i] <= lw.iloc[i-1] and lw.iloc[i] <= lw.iloc[i+1] and lw.iloc[i] <= lw.iloc[i-2] and lw.iloc[i] <= lw.iloc[i+2]:
                sl.append((i, lw.iloc[i], float(rw.iloc[i])))
            if hw.iloc[i] >= hw.iloc[i-1] and hw.iloc[i] >= hw.iloc[i+1] and hw.iloc[i] >= hw.iloc[i-2] and hw.iloc[i] >= hw.iloc[i+2]:
                sh.append((i, hw.iloc[i], float(rw.iloc[i])))
        pn, rn = float(cw.iloc[-1]), float(rw.iloc[-1])
        if len(sl) >= 2:
            pv, lv = sl[-2], sl[-1]
            if lv[1] < pv[1] and lv[2] > pv[2] and rn < 45:
                st = int(_clamp((lv[2]-pv[2])*3+(pv[1]-lv[1])/pv[1]*100, 1, 10))
                return {"divergence": "BULLISH", "strength": st, "type": "REGULAR", "price_now": pn, "rsi_now": rn}
            if lv[1] > pv[1] and lv[2] < pv[2] and rn > 45:
                st = int(_clamp((pv[2]-lv[2])*2+(lv[1]-pv[1])/pv[1]*100, 1, 8))
                return {"divergence": "BULLISH", "strength": st, "type": "HIDDEN", "price_now": pn, "rsi_now": rn}
        if len(sh) >= 2:
            pv, lv = sh[-2], sh[-1]
            if lv[1] > pv[1] and lv[2] < pv[2] and rn > 55:
                st = int(_clamp((pv[2]-lv[2])*3+(lv[1]-pv[1])/pv[1]*100, 1, 10))
                return {"divergence": "BEARISH", "strength": st, "type": "REGULAR", "price_now": pn, "rsi_now": rn}
            if lv[1] < pv[1] and lv[2] > pv[2] and rn < 55:
                st = int(_clamp((lv[2]-pv[2])*2+(pv[1]-lv[1])/pv[1]*100, 1, 8))
                return {"divergence": "BEARISH", "strength": st, "type": "HIDDEN", "price_now": pn, "rsi_now": rn}
        return d
    except Exception:
        return d


# -----------------------------------------------------------------------------
# 4. VOLATILITY REGIME
# -----------------------------------------------------------------------------
def detect_volatility_regime(candles: pd.DataFrame, p: int = 20) -> dict:
    d = {"regime": "MEDIUM", "atr_pct": 3.0, "volatility_score": 50, "trend_reliability": "MODERATE"}
    if candles is None or candles.empty or len(candles) < p + 10:
        return d
    try:
        h, lo, c = [candles[x].astype(float) for x in ("high", "low", "close")]
        tr = pd.concat([h - lo, (h - c.shift(1)).abs(), (lo - c.shift(1)).abs()], axis=1).max(axis=1)
        atr = tr.rolling(p).mean().iloc[-1]
        price = float(c.iloc[-1])
        ap = (atr / price * 100) if price > 0 else 3.0
        vs = _clamp(ap * 10, 0, 100)
        if ap < 1.5:
            rg, rl = "LOW", "LOW"
        elif ap < 3.5:
            rg, rl = "MEDIUM", "MODERATE"
        elif ap < 6.0:
            rg, rl = "HIGH", "HIGH"
        else:
            rg, rl = "EXTREME", "LOW"
        ao = float(tr.rolling(p).mean().iloc[-5]) if len(tr) > 5 else atr
        vc = (atr - ao) / ao * 100 if ao > 0 else 0
        return {"regime": rg, "atr_pct": round(ap, 2), "volatility_score": round(vs, 1),
                "trend_reliability": rl, "vol_change_pct": round(vc, 1),
                "is_expanding": vc > 10, "is_contracting": vc < -10}
    except Exception:
        return d


# -----------------------------------------------------------------------------
# 5. ORDER FLOW IMBALANCE
# -----------------------------------------------------------------------------
def compute_order_flow(candles: pd.DataFrame) -> dict:
    d = {"buy_pressure": 50, "sell_pressure": 50, "net_flow": 0,
         "flow_strength": "NEUTRAL", "pressure_trend": "FLAT"}
    if candles is None or candles.empty or len(candles) < 20:
        return d
    try:
        c, h, lo, v = [candles[x].astype(float) for x in ("close", "high", "low", "volume")]
        rng = h - lo
        cp = (c - lo) / rng.replace(0, np.nan)
        bv = v.where(cp > 0.7, 0).sum()
        sv = v.where(cp < 0.3, 0).sum()
        t = bv + sv
        if t <= 0:
            return d
        bp, sp = bv / t * 100, sv / t * 100
        nf = bp - sp
        fs = "STRONG" if abs(nf) > 30 else "MODERATE" if abs(nf) > 15 else "WEAK"
        rb, ob = cp.tail(5).mean() * 100, cp.tail(10).head(5).mean() * 100
        pt = "INCREASING" if rb - ob > 10 else "DECREASING" if rb - ob < -10 else "FLAT"
        return {"buy_pressure": round(bp, 1), "sell_pressure": round(sp, 1),
                "net_flow": round(nf, 1), "flow_strength": fs, "pressure_trend": pt}
    except Exception:
        return d


# -----------------------------------------------------------------------------
# 6. FIBONACCI EXTENSIONS
# -----------------------------------------------------------------------------
def compute_fib_extensions(candles: pd.DataFrame, lb: int = 120) -> dict:
    d = {"ext_618": None, "ext_1000": None, "ext_1618": None, "ext_2618": None,
         "ext_4236": None, "extension_zone": "NO DATA"}
    if candles is None or candles.empty or len(candles) < 30:
        return d
    try:
        h, lo, c = [candles[x].astype(float) for x in ("high", "low", "close")]
        sl, sh = float(lo.min()), float(h.max())
        lp = float(c.iloc[-1])
        if sh == sl:
            return d
        move = sh - sl
        ext = {f"ext_{int(f*1000)}": sh + move * f for f in [0.618, 1.0, 1.618, 2.618, 4.236]}
        zone = "BEYOND EXTENSION" if lp > sh * 1.02 else "AT EXTREME" if lp >= sh else "WITHIN EXTENSION" if lp >= sh - move * 0.236 else "BELOW EXTENSION"
        return {"ext_618": ext["ext_618"], "ext_1000": ext["ext_1000"],
                "ext_1618": ext["ext_1618"], "ext_2618": ext["ext_2618"],
                "ext_4236": ext["ext_4236"], "extension_zone": zone}
    except Exception:
        return d


# -----------------------------------------------------------------------------
# 7. WYCKOFF PHASE
# -----------------------------------------------------------------------------
def detect_wyckoff(candles: pd.DataFrame, lb: int = 60) -> dict:
    d = {"phase": "UNKNOWN", "confidence": "LOW", "signal": "NONE"}
    if candles is None or candles.empty or len(candles) < 40:
        return d
    try:
        c, h, lo, v = [candles[x].astype(float) for x in ("close", "high", "low", "volume")]
        pr = float(h.max() - lo.min())
        if pr <= 0:
            return d
        lp = float(c.iloc[-1])
        pp = (lp - float(lo.min())) / pr
        ve, vl = v.head(lb // 2).mean(), v.tail(lb // 2).mean()
        vt = (vl - ve) / ve if ve > 0 else 0
        pe, pls = float(c.iloc[lb // 2]), float(c.iloc[-1])
        pt = (pls - pe) / pe if pe > 0 else 0
        vr, vo = v.tail(5).mean(), v.tail(15).head(10).mean()
        vs = (vr - vo) / vo if vo > 0 else 0
        if abs(pt) < 0.1 and vs < -0.2 and pp > 0.6:
            return {"phase": "ACCUMULATION", "confidence": "HIGH" if vs < -0.4 else "MEDIUM",
                    "signal": "BUY", "price_position": round(pp * 100, 1), "volume_trend": round(vt * 100, 1)}
        if pp > 0.7 and vs < -0.2 and pt > 0:
            return {"phase": "DISTRIBUTION", "confidence": "HIGH" if vs < -0.4 else "MEDIUM",
                    "signal": "SELL", "price_position": round(pp * 100, 1), "volume_trend": round(vt * 100, 1)}
        if pt > 0.1 and pp > 0.5:
            return {"phase": "TRENDING_UP", "confidence": "MEDIUM", "signal": "HOLD"}
        if pt < -0.1 and pp < 0.5:
            return {"phase": "TRENDING_DOWN", "confidence": "MEDIUM", "signal": "AVOID"}
        return {"phase": "RANGING", "confidence": "LOW", "signal": "WAIT", "price_position": round(pp * 100, 1)}
    except Exception:
        return d


# -----------------------------------------------------------------------------
# 8. STOCHASTIC RSI
# -----------------------------------------------------------------------------
def compute_stoch_rsi(candles: pd.DataFrame, rsi_p: int = 14, stoch_p: int = 14) -> dict:
    d = {"stoch_rsi": 50, "stoch_rsi_signal": "NEUTRAL", "k_value": 50, "d_value": 50}
    if candles is None or candles.empty or len(candles) < 30:
        return d
    try:
        c = candles["close"].astype(float)
        delta = c.diff()
        gain = delta.clip(lower=0).ewm(alpha=1/rsi_p, adjust=False).mean()
        loss = (-delta.clip(upper=0)).ewm(alpha=1/rsi_p, adjust=False).mean()
        rsi = 100 - (100 / (1 + gain / loss.replace(0, np.nan)))
        lr, hr = rsi.rolling(stoch_p).min(), rsi.rolling(stoch_p).max()
        k = (rsi - lr) / (hr - lr).replace(0, np.nan) * 100
        dv = k.rolling(3).mean()
        kv, dvv = float(k.iloc[-1]), float(dv.iloc[-1])
        sig = "OVERSOLD" if kv < 20 else "OVERBOUGHT" if kv > 80 else "WEAK" if kv < 40 else "STRONG" if kv > 60 else "NEUTRAL"
        if len(k) > 1:
            pk = float(k.iloc[-2])
            if pk < dvv and kv > dvv and kv < 20:
                sig = "BULLISH CROSS"
            elif pk > dvv and kv > dvv and kv > 80:
                sig = "BEARISH CROSS"
        return {"stoch_rsi": round(kv, 1), "stoch_rsi_signal": sig,
                "k_value": round(kv, 1), "d_value": round(dvv, 1)}
    except Exception:
        return d


# -----------------------------------------------------------------------------
# 9. COMMODITY CHANNEL INDEX (CCI)
# -----------------------------------------------------------------------------
def compute_cci(candles: pd.DataFrame, p: int = 20) -> dict:
    d = {"cci": 0, "cci_signal": "NEUTRAL"}
    if candles is None or candles.empty or len(candles) < p + 10:
        return d
    try:
        h, lo, c = [candles[x].astype(float) for x in ("high", "low", "close")]
        tp = (h + lo + c) / 3
        ma = tp.rolling(p).mean()
        md = tp.rolling(p).apply(lambda x: np.mean(np.abs(x - np.mean(x))), raw=True)
        cci = (tp - ma) / (0.015 * md.replace(0, np.nan))
        cv = float(cci.iloc[-1])
        sig = "OVERBOUGHT" if cv > 100 else "OVERSOLD" if cv < -100 else "STRONG" if cv > 50 else "WEAK" if cv < -50 else "NEUTRAL"
        if len(cci) > 1:
            pc = float(cci.iloc[-2])
            if pc < 0 and cv > 0:
                sig = "BULLISH CROSS"
            elif pc > 0 and cv < 0:
                sig = "BEARISH CROSS"
        return {"cci": round(cv, 1), "cci_signal": sig}
    except Exception:
        return d


# -----------------------------------------------------------------------------
# 10. PRICE ACTION PATTERNS
# -----------------------------------------------------------------------------
def detect_price_action(candles: pd.DataFrame) -> dict:
    d = {"pattern": "NONE", "pattern_strength": "WEAK", "inside_bars": 0,
         "outside_bars": 0, "gaps": 0, "inside_pct": 0.0, "outside_pct": 0.0}
    if candles is None or candles.empty or len(candles) < 10:
        return d
    try:
        c, h, lo = [candles[x].astype(float) for x in ("close", "high", "low")]
        op = candles["open"].astype(float) if "open" in candles.columns else c.shift(1)
        ib, ob, gp = 0, 0, 0
        for i in range(1, len(candles)):
            ph, pl = h.iloc[i-1], lo.iloc[i-1]
            ch, cl = h.iloc[i], lo.iloc[i]
            if ch <= ph and cl >= pl:
                ib += 1
            if ch >= ph and cl <= pl:
                ob += 1
            co = float(op.iloc[i])
            if co > ph * 1.01 or co < pl * 0.99:
                gp += 1
        tb = len(candles)
        ip, opct = ib / tb * 100, ob / tb * 100
        if ip > 30:
            pat, st = "CONSOLIDATION (Inside Bars)", "MODERATE"
        elif opct > 20:
            pat, st = "EXPANSION (Outside Bars)", "MODERATE"
        elif gp > 2:
            pat, st = "GAP ACTIVITY", "STRONG"
        else:
            pat, st = "NORMAL TRADING", "WEAK"
        return {"pattern": pat, "pattern_strength": st, "inside_bars": ib,
                "outside_bars": ob, "gaps": gp, "inside_pct": round(ip, 1), "outside_pct": round(opct, 1)}
    except Exception:
        return d


# -----------------------------------------------------------------------------
# 11. MONEY FLOW STRENGTH
# -----------------------------------------------------------------------------
def compute_money_flow_strength(candles: pd.DataFrame) -> dict:
    d = {"mfs": 0, "mfs_signal": "NEUTRAL", "volume_confirmed": False}
    if candles is None or candles.empty or len(candles) < 20:
        return d
    try:
        c, h, lo, v = [candles[x].astype(float) for x in ("close", "high", "low", "volume")]
        tp = (h + lo + c) / 3
        pc = c.pct_change()
        mf = pc * v
        pos = mf[mf > 0].sum()
        neg = abs(mf[mf < 0].sum())
        if neg <= 0:
            mfs = 100 if pos > 0 else 0
        elif pos <= 0:
            mfs = -100 if neg > 0 else 0
        else:
            mfs = (pos - neg) / (pos + neg) * 100
        sig = "STRONG BUY" if mfs > 50 else "BULLISH" if mfs > 20 else "STRONG SELL" if mfs < -50 else "BEARISH" if mfs < -20 else "NEUTRAL"
        vc = v.tail(5).mean() > v.tail(20).mean() * 1.2
        return {"mfs": round(mfs, 1), "mfs_signal": sig, "volume_confirmed": vc,
                "pos_flow": round(float(pos), 2), "neg_flow": round(float(neg), 2)}
    except Exception:
        return d


# -----------------------------------------------------------------------------
# 12. BREAKOUT DETECTION
# -----------------------------------------------------------------------------
def detect_breakout(candles: pd.DataFrame, lb: int = 50) -> dict:
    d = {"breakout": "NONE", "direction": "NONE", "strength": "WEAK",
         "consolidation_bars": 0, "volume_spike": False}
    if candles is None or candles.empty or len(candles) < lb + 10:
        return d
    try:
        c, h, lo, v = [candles[x].astype(float) for x in ("close", "high", "low", "volume")]
        recent = candles.tail(lb)
        rh, rl = float(recent["high"].astype(float).max()), float(recent["low"].astype(float).min())
        mid = (rh + rl) / 2
        if mid == 0:
            return d
        range_pct = (rh - rl) / mid * 100
        # Consolidation = banyak bar di range sempit
        con = 0
        for i in range(1, lb):
            bar_range = (h.iloc[-i] - lo.iloc[-i]) / mid * 100
            if bar_range < range_pct * 0.3:
                con += 1
        last = float(c.iloc[-1])
        prev = float(c.iloc[-2])
        vol_recent = v.tail(3).mean()
        vol_avg = v.tail(20).mean()
        vol_spike = vol_recent > vol_avg * 1.5
        if last > rh and prev <= rh:
            return {"breakout": "CONFIRMED", "direction": "UP", "strength": "STRONG" if vol_spike else "MODERATE",
                    "consolidation_bars": con, "volume_spike": vol_spike}
        elif last < rl and prev >= rl:
            return {"breakout": "CONFIRMED", "direction": "DOWN", "strength": "STRONG" if vol_spike else "MODERATE",
                    "consolidation_bars": con, "volume_spike": vol_spike}
        elif last > rh * 0.99 and last < rh:
            return {"breakout": "PENDING", "direction": "UP", "strength": "WEAK",
                    "consolidation_bars": con, "volume_spike": vol_spike}
        elif last < rl * 1.01 and last > rl:
            return {"breakout": "PENDING", "direction": "DOWN", "strength": "WEAK",
                    "consolidation_bars": con, "volume_spike": vol_spike}
        return {"breakout": "NONE", "direction": "NONE", "strength": "WEAK",
                "consolidation_bars": con, "volume_spike": vol_spike}
    except Exception:
        return d


# -----------------------------------------------------------------------------
# 13. MEAN REVERSION SCORE
# -----------------------------------------------------------------------------
def compute_mean_reversion(candles: pd.DataFrame, p: int = 20) -> dict:
    d = {"deviation_pct": 0, "mean_price": None, "reversion_score": 0,
         "reversion_signal": "NEUTRAL", "z_score": 0}
    if candles is None or candles.empty or len(candles) < p + 5:
        return d
    try:
        c = candles["close"].astype(float)
        ma = c.rolling(p).mean().iloc[-1]
        std = c.rolling(p).std().iloc[-1]
        lp = float(c.iloc[-1])
        dev = (lp - ma) / ma * 100 if ma > 0 else 0
        zs = (lp - ma) / std if std > 0 else 0
        rs = min(abs(dev) * 2, 100)
        if dev > 5 and zs > 2:
            sig = "OVEREXTENDED - REVERSION DOWN LIKELY"
        elif dev < -5 and zs < -2:
            sig = "OVERSOLD - REVERSION UP LIKELY"
        elif abs(dev) < 1 and abs(zs) < 0.5:
            sig = "AT EQUILIBRIUM"
        elif dev > 2:
            sig = "ABOVE MEAN"
        elif dev < -2:
            sig = "BELOW MEAN"
        else:
            sig = "NEAR MEAN"
        return {"deviation_pct": round(dev, 2), "mean_price": round(float(ma), 6),
                "reversion_score": round(rs, 1), "reversion_signal": sig, "z_score": round(zs, 2)}
    except Exception:
        return d


# -----------------------------------------------------------------------------
# 14. TREND STRENGTH INDEX
# -----------------------------------------------------------------------------
def compute_trend_strength(candles: pd.DataFrame) -> dict:
    d = {"trend_strength": 0, "trend_direction": "NEUTRAL", "trend_quality": "LOW"}
    if candles is None or candles.empty or len(candles) < 30:
        return d
    try:
        c, h, lo = [candles[x].astype(float) for x in ("close", "high", "low")]
        # ADX-like calculation
        tr = pd.concat([h - lo, (h - c.shift(1)).abs(), (lo - c.shift(1)).abs()], axis=1).max(axis=1)
        plus_dm = (h - h.shift(1)).clip(lower=0)
        minus_dm = (lo.shift(1) - lo).clip(lower=0)
        plus_dm = plus_dm.where(plus_dm > minus_dm, 0)
        minus_dm = minus_dm.where(minus_dm > plus_dm, 0)
        atr14 = tr.rolling(14).mean()
        plus_di = 100 * plus_dm.rolling(14).mean() / atr14.replace(0, np.nan)
        minus_di = 100 * minus_dm.rolling(14).mean() / atr14.replace(0, np.nan)
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di).replace(0, np.nan)
        adx = dx.rolling(14).mean()
        adx_val = float(adx.iloc[-1]) if not pd.isna(adx.iloc[-1]) else 0
        plus_val = float(plus_di.iloc[-1]) if not pd.isna(plus_di.iloc[-1]) else 0
        minus_val = float(minus_di.iloc[-1]) if not pd.isna(minus_di.iloc[-1]) else 0
        if adx_val > 40:
            quality = "VERY STRONG"
        elif adx_val > 25:
            quality = "STRONG"
        elif adx_val > 15:
            quality = "MODERATE"
        else:
            quality = "WEAK"
        if plus_val > minus_val and adx_val > 20:
            direction = "BULLISH"
        elif minus_val > plus_val and adx_val > 20:
            direction = "BEARISH"
        else:
            direction = "NEUTRAL"
        return {"trend_strength": round(adx_val, 1), "trend_direction": direction,
                "trend_quality": quality, "plus_di": round(plus_val, 1), "minus_di": round(minus_val, 1)}
    except Exception:
        return d


# -----------------------------------------------------------------------------
# 15. SUPPLY/DEMAND ZONES
# -----------------------------------------------------------------------------
def compute_supply_demand_zones(candles: pd.DataFrame, lookback: int = 60) -> dict:
    d = {"demand_zones": [], "supply_zones": [], "nearest_zone": None,
         "zone_signal": "NONE", "price_position": "NEUTRAL"}
    if candles is None or candles.empty or len(candles) < 30:
        return d
    try:
        c, h, lo = [candles[x].astype(float) for x in ("close", "high", "low")]
        price = float(c.iloc[-1])
        recent = candles.tail(lookback)
        rc, rh, rl = [recent[x].astype(float) for x in ("close", "high", "low")]
        # Demand zones: bases with strong bounce (higher lows consolidation + breakout)
        demands, supplies = [], []
        for i in range(3, len(recent) - 3):
            # Demand: price made base, then rallied
            if rl.iloc[i] < rl.iloc[i-1] and rl.iloc[i] < rl.iloc[i+1] and rc.iloc[i+3] > rc.iloc[i] * 1.03:
                demands.append({"top": float(rh.iloc[i]), "bottom": float(rl.iloc[i]),
                                "strength": int((rc.iloc[i+3] / rc.iloc[i] - 1) * 100)})
            # Supply: price made peak, then dropped
            if rh.iloc[i] > rh.iloc[i-1] and rh.iloc[i] > rh.iloc[i+1] and rc.iloc[i+3] < rc.iloc[i] * 0.97:
                supplies.append({"top": float(rh.iloc[i]), "bottom": float(rl.iloc[i]),
                                 "strength": int((1 - rc.iloc[i+3] / rc.iloc[i]) * 100)})
        demands.sort(key=lambda x: x["strength"], reverse=True)
        supplies.sort(key=lambda x: x["strength"], reverse=True)
        # Find nearest zone
        nearest = None
        min_dist = float('inf')
        for zone in demands[:3]:
            if price > zone["bottom"]:
                dist = abs(price - zone["bottom"]) / price * 100
                if dist < min_dist:
                    min_dist = dist
                    nearest = {"type": "DEMAND", "zone": zone, "distance": round(dist, 2)}
        for zone in supplies[:3]:
            if price < zone["top"]:
                dist = abs(price - zone["top"]) / price * 100
                if dist < min_dist:
                    min_dist = dist
                    nearest = {"type": "SUPPLY", "zone": zone, "distance": round(dist, 2)}
        # Price position relative to zones
        if nearest:
            if nearest["type"] == "DEMAND" and nearest["distance"] < 2:
                ps = "AT DEMAND - BULLISH BIAS"
            elif nearest["type"] == "SUPPLY" and nearest["distance"] < 2:
                ps = "AT SUPPLY - BEARISH BIAS"
            elif nearest["type"] == "DEMAND":
                ps = "ABOVE DEMAND - HOLD"
            else:
                ps = "BELOW SUPPLY - AVOID"
        else:
            ps = "NO ZONE NEARBY"
        return {"demand_zones": demands[:3], "supply_zones": supplies[:3],
                "nearest_zone": nearest, "zone_signal": nearest["type"] if nearest else "NONE",
                "price_position": ps}
    except Exception:
        return d


# =============================================================================
# MASTER BUNDLE - All algorithms in one call
# =============================================================================
def build_advanced_bundle(candles: pd.DataFrame) -> dict:
    """Jalankan semua algoritma advanced dalam satu call."""
    return {
        "volume_profile": compute_volume_profile(candles),
        "sr_strength": compute_sr_strength(candles),
        "rsi_divergence": detect_rsi_divergence(candles),
        "volatility_regime": detect_volatility_regime(candles),
        "order_flow": compute_order_flow(candles),
        "fib_extensions": compute_fib_extensions(candles),
        "wyckoff": detect_wyckoff(candles),
        "stoch_rsi": compute_stoch_rsi(candles),
        "cci": compute_cci(candles),
        "price_action": detect_price_action(candles),
        "money_flow": compute_money_flow_strength(candles),
        "breakout": detect_breakout(candles),
        "mean_reversion": compute_mean_reversion(candles),
        "trend_strength": compute_trend_strength(candles),
        "supply_demand": compute_supply_demand_zones(candles),
    }


# =============================================================================
# SCORING INTEGRATION - Adjust signal score from advanced algos
# =============================================================================
def compute_advanced_adjustment(bundle: dict) -> tuple[int, list[str]]:
    """Konversi output advanced algorithms jadi score adjustment + notes."""
    adjust = 0
    notes = []

    # Volume Profile
    vp = bundle.get("volume_profile", {})
    if vp.get("poc"):
        notes.append(f"VP POC: {vp['poc']:.6f}")
    if vp.get("profile_shape") == "LEFT-HEAVY (BULLISH)":
        adjust += 2
        notes.append("VP left-heavy bullish (+2)")
    elif vp.get("profile_shape") == "RIGHT-HEAVY (BEARISH)":
        adjust -= 2
        notes.append("VP right-heavy bearish (-2)")

    # SR Strength
    sr = bundle.get("sr_strength", {})
    if sr.get("strongest_sr"):
        ssr = sr["strongest_sr"]
        notes.append(f"SR: {ssr['price']:.6f} (str {ssr['strength']}, touches {ssr['touches']})")

    # RSI Divergence
    rd = bundle.get("rsi_divergence", {})
    if rd.get("divergence") == "BULLISH" and rd.get("type") == "REGULAR":
        adjust += 5
        notes.append(f"RSI bullish regular div st{rd['strength']} (+5)")
    elif rd.get("divergence") == "BULLISH" and rd.get("type") == "HIDDEN":
        adjust += 3
        notes.append(f"RSI bullish hidden div st{rd['strength']} (+3)")
    elif rd.get("divergence") == "BEARISH" and rd.get("type") == "REGULAR":
        adjust -= 5
        notes.append(f"RSI bearish regular div st{rd['strength']} (-5)")
    elif rd.get("divergence") == "BEARISH" and rd.get("type") == "HIDDEN":
        adjust -= 3
        notes.append(f"RSI bearish hidden div st{rd['strength']} (-3)")

    # Volatility Regime
    vr = bundle.get("volatility_regime", {})
    if vr.get("regime") == "EXTREME":
        notes.append("EXTREME VOLATILITY - proceed with caution")
    if vr.get("is_contracting"):
        adjust += 1
        notes.append("Vol contracting - breakout setup (+1)")

    # Order Flow
    of = bundle.get("order_flow", {})
    if of.get("flow_strength") == "STRONG" and of.get("net_flow", 0) > 20:
        adjust += 3
        notes.append(f"Strong buy flow {of['net_flow']:.0f}% (+3)")
    elif of.get("flow_strength") == "STRONG" and of.get("net_flow", 0) < -20:
        adjust -= 3
        notes.append(f"Strong sell flow {of['net_flow']:.0f}% (-3)")

    # Wyckoff
    wy = bundle.get("wyckoff", {})
    if wy.get("phase") == "ACCUMULATION":
        adjust += 4
        notes.append("Wyckoff accumulation (+4)")
    elif wy.get("phase") == "DISTRIBUTION":
        adjust -= 4
        notes.append("Wyckoff distribution (-4)")
    elif wy.get("phase") == "TRENDING_UP":
        adjust += 2
        notes.append("Wyckoff trending up (+2)")
    elif wy.get("phase") == "TRENDING_DOWN":
        adjust -= 2
        notes.append("Wyckoff trending down (-2)")

    # Stoch RSI
    st = bundle.get("stoch_rsi", {})
    if st.get("stoch_rsi_signal") == "BULLISH CROSS":
        adjust += 3
        notes.append(f"StochRSI bullish cross K{st['k_value']:.0f} (+3)")
    elif st.get("stoch_rsi_signal") == "BEARISH CROSS":
        adjust -= 3
        notes.append(f"StochRSI bearish cross K{st['k_value']:.0f} (-3)")
    elif st.get("stoch_rsi_signal") == "OVERSOLD":
        adjust += 2
        notes.append("StochRSI oversold (+2)")
    elif st.get("stoch_rsi_signal") == "OVERBOUGHT":
        adjust -= 2
        notes.append("StochRSI overbought (-2)")

    # CCI
    cci = bundle.get("cci", {})
    if cci.get("cci_signal") == "BULLISH CROSS":
        adjust += 2
        notes.append("CCI bullish cross (+2)")
    elif cci.get("cci_signal") == "BEARISH CROSS":
        adjust -= 2
        notes.append("CCI bearish cross (-2)")

    # Breakout
    bo = bundle.get("breakout", {})
    if bo.get("breakout") == "CONFIRMED" and bo.get("direction") == "UP":
        adjust += 5
        notes.append(f"Breakout UP {bo['strength']} (+5)")
    elif bo.get("breakout") == "CONFIRMED" and bo.get("direction") == "DOWN":
        adjust -= 5
        notes.append(f"Breakout DOWN {bo['strength']} (-5)")
    elif bo.get("breakout") == "PENDING":
        notes.append(f"Breakout pending {bo['direction']}")

    # Mean Reversion
    mr = bundle.get("mean_reversion", {})
    if "REVERSION DOWN" in mr.get("reversion_signal", ""):
        adjust -= 2
        notes.append(f"Overextended z{mr['z_score']:.1f} (-2)")
    elif "REVERSION UP" in mr.get("reversion_signal", ""):
        adjust += 2
        notes.append(f"Oversold z{mr['z_score']:.1f} (+2)")

    # Trend Strength
    ts = bundle.get("trend_strength", {})
    if ts.get("trend_direction") == "BULLISH" and ts.get("trend_quality") in ("STRONG", "VERY STRONG"):
        adjust += 3
        notes.append(f"Strong bull trend ADX{ts['trend_strength']:.0f} (+3)")
    elif ts.get("trend_direction") == "BEARISH" and ts.get("trend_quality") in ("STRONG", "VERY STRONG"):
        adjust -= 3
        notes.append(f"Strong bear trend ADX{ts['trend_strength']:.0f} (-3)")

    # Supply/Demand
    sd = bundle.get("supply_demand", {})
    if sd.get("zone_signal") == "DEMAND":
        adjust += 2
        notes.append("At demand zone (+2)")
    elif sd.get("zone_signal") == "SUPPLY":
        adjust -= 2
        notes.append("At supply zone (-2)")

    adjust = max(-20, min(18, adjust))
    return adjust, notes[:6]

"""
AI Auto-Pilot
=============
Modul yang men-generate "Playbook Hari Ini" — perintah ringkas dari AI
yang merangkum apa yang sebaiknya dilakukan user berdasarkan:

- Top picks dari rekomendasi engine (dengan ramalan 6h/24h)
- Portfolio terbuka user (P/L per posisi, action sinyal saat ini)
- Market mode (aggressive/normal/defensive)
- News sentiment global
- Learning profile (winrate historis bot)

AI **tidak** execute trade — cuma kasih instruksi ringkas yang user
eksekusi manual. Tidak butuh API key Indodax.

Output terstruktur (Markdown):
    🌤  Outlook Pasar
    🎯 Aksi Prioritas (3-5 instruksi spesifik)
    💼 Review Portfolio (kalau ada posisi)
    ⚠️  Hindari (kalau relevan)
    📌 Catatan Penutup

Cached 5 menit per snapshot supaya hemat quota AI.
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from typing import Any


def _format_price(value: float) -> str:
    if value is None or value == 0:
        return "-"
    if value >= 1_000_000:
        return f"Rp{value/1_000_000:.2f}JT"
    if value >= 1_000:
        return f"Rp{value:,.0f}"
    if value >= 1:
        return f"Rp{value:,.2f}"
    return f"Rp{value:,.6f}"


def _format_idr(value: float) -> str:
    if value is None or value == 0:
        return "Rp0"
    if value >= 1_000_000_000:
        return f"Rp{value/1_000_000_000:.2f}M"
    if value >= 1_000_000:
        return f"Rp{value/1_000_000:.1f}JT"
    if value >= 1_000:
        return f"Rp{value:,.0f}"
    return f"Rp{value:,.0f}"


def build_pilot_context(
    market_stats: dict | None,
    top_picks: list[dict],
    portfolio_positions: list[dict] | None,
    portfolio_capital_idr: float,
    news_profile: dict | None,
    learning_profile: dict | None,
    tickers: dict | None = None,
) -> dict:
    """Rangkum semua data jadi struktur context yang LLM-friendly."""
    ctx: dict[str, Any] = {}

    # Market mode
    if market_stats:
        ctx["market"] = {
            "mode": market_stats.get("mode", "normal"),
            "green_pct": market_stats.get("green_pct", 0),
            "avg_change": market_stats.get("avg_change", 0),
            "total_pairs": market_stats.get("total_pairs", 0),
        }
    else:
        ctx["market"] = {"mode": "normal"}

    # Top buy picks (cuma yang BELI KUAT/CICIL BELI)
    picks_summary = []
    for p in top_picks[:5]:
        picks_summary.append({
            "symbol": p["symbol"],
            "price": p["price"],
            "change_pct": p.get("change", 0),
            "score": p.get("score", 0),
            "action": p.get("action", "WATCH"),
            "risk": p.get("risk_level", "SEDANG"),
            "alloc_pct": p.get("allocation_pct", 0),
            "tp1": p.get("tp1", 0),
            "tp2": p.get("tp2", 0),
            "target": p.get("target", 0),
            "stop_loss": p.get("stop_loss", 0),
            "entry_zone_low": p.get("entry_zone_low", 0),
            "entry_zone_high": p.get("entry_zone_high", 0),
            "forecast_6h_prob": p.get("forecast_step1_prob", 50),
            "forecast_6h_conf": p.get("forecast_step1_conf", "rendah"),
            "forecast_24h_prob": p.get("forecast_step2_prob", 50),
            "forecast_24h_conf": p.get("forecast_step2_conf", "rendah"),
            "intel_confidence": p.get("intel_confidence", "LEMAH"),
            "confluence_passed": p.get("confluence_passed", 0),
            "mtf_label": p.get("mtf_label", "MIXED"),
            "regime": p.get("regime", "MIXED"),
        })
    ctx["top_picks"] = picks_summary

    # Portfolio
    if portfolio_positions:
        pf_rows = []
        total_cost = 0.0
        total_value = 0.0
        for pos in portfolio_positions:
            pair = pos.get("pair") or f"{pos['symbol'].lower()}_idr"
            cur_price = float((tickers or {}).get(pair, {}).get("last", 0) or 0)
            qty = float(pos.get("qty", 0) or 0)
            avg_buy = float(pos.get("avg_buy_price", 0) or 0)
            cost = qty * avg_buy
            value_now = qty * cur_price
            pnl_pct = ((cur_price - avg_buy) / avg_buy * 100) if avg_buy > 0 else 0
            total_cost += cost
            total_value += value_now
            pf_rows.append({
                "symbol": pos["symbol"],
                "qty": qty,
                "avg_buy": avg_buy,
                "current_price": cur_price,
                "pnl_pct": round(pnl_pct, 2),
                "cost": cost,
                "value_now": value_now,
            })
        # Rec untuk setiap posisi (apa sinyal sekarang?)
        for r in pf_rows:
            for p in top_picks:
                if p["symbol"] == r["symbol"]:
                    r["current_action"] = p.get("action", "—")
                    r["current_score"] = p.get("score", None)
                    break
        ctx["portfolio"] = {
            "total_cost": total_cost,
            "total_value": total_value,
            "pnl_pct": round((total_value - total_cost) / total_cost * 100, 2) if total_cost > 0 else 0,
            "exposure_pct": round(total_cost / portfolio_capital_idr * 100, 1) if portfolio_capital_idr > 0 else None,
            "capital_idr": portfolio_capital_idr,
            "positions": pf_rows,
        }
    else:
        ctx["portfolio"] = {"positions": []}

    # News
    if news_profile:
        ctx["news"] = {
            "global_label": news_profile.get("global_label", "NEUTRAL"),
            "global_score": news_profile.get("global_score", 0),
            "top_headlines": [
                {"title": a.get("title", "")[:120], "source": a.get("source", ""), "score": a.get("score", 0)}
                for a in (news_profile.get("articles", []) or [])[:3]
            ],
        }

    # Learning
    if learning_profile:
        ctx["learning"] = {
            "winrate": learning_profile.get("winrate"),
            "closed": learning_profile.get("closed", 0),
            "active": learning_profile.get("active", 0),
            "best_symbols": [
                {"symbol": sym, "winrate": stats.get("winrate", 0), "trades": stats.get("closed", 0)}
                for sym, stats in (learning_profile.get("best_symbols", []) or [])[:3]
            ],
        }

    return ctx


def _hash_context(ctx: dict) -> str:
    """Hash context untuk caching. Kita pakai harga/score sebagai signature
    supaya cache invalidate saat market berubah signifikan.

    Untuk harga, pakai relative bucket (0.5%) supaya coin micro-price (PEPE/SHIB
    yang harganya 0.00001) dan coin Rp1JT-an sama-sama detect perubahan ~0.5%.
    Round absolut akan bias ke salah satu skala.
    """
    def _price_bucket(price: float) -> int:
        """Bucket relatif: setiap 0.5% perubahan dianggap sinyal cache invalidate."""
        if price <= 0:
            return 0
        # log10(price * 200) → setiap 0.5% beda menghasilkan bucket berbeda
        try:
            return int(round(math.log(max(price, 1e-12)) * 200, 0))
        except (ValueError, OverflowError):
            return 0

    sig = {
        "mode": ctx.get("market", {}).get("mode"),
        "picks": [
            (p["symbol"], _price_bucket(float(p.get("price", 0))), p["score"], p["action"])
            for p in ctx.get("top_picks", [])
        ],
        "pnl": [
            (r["symbol"], round(r.get("pnl_pct", 0), 1), r.get("current_action", ""))
            for r in ctx.get("portfolio", {}).get("positions", [])
        ],
    }
    return hashlib.md5(json.dumps(sig, sort_keys=True).encode()).hexdigest()[:12]


def render_pilot_prompt(ctx: dict) -> str:
    """Susun prompt yang dikirim ke LLM. Bahasa Indonesia, struktur clear."""
    market = ctx.get("market", {})
    picks = ctx.get("top_picks", [])
    pf = ctx.get("portfolio", {})
    news = ctx.get("news", {})
    learn = ctx.get("learning", {})

    lines = [
        "Kamu adalah AI Pilot crypto trading yang membantu user mengeksekusi keputusan harian.",
        "Generate **Playbook Hari Ini** dalam bahasa Indonesia yang ringkas, actionable, dan jujur.",
        "",
        "DATA SAAT INI:",
        f"- Market mode: {market.get('mode', 'normal').upper()} ({market.get('green_pct', 0)}% hijau, avg {market.get('avg_change', 0):+.2f}%)",
    ]

    if news:
        lines.append(f"- Sentimen berita global: {news.get('global_label', 'NEUTRAL')} (score {news.get('global_score', 0):+.2f})")

    if learn and learn.get("winrate") is not None:
        lines.append(f"- Bot historis: {learn['winrate']:.1f}% winrate dari {learn['closed']} trade selesai")
        if learn.get("best_symbols"):
            best_str = ", ".join(f"{b['symbol']} {b['winrate']:.0f}%" for b in learn["best_symbols"])
            lines.append(f"  Top performers: {best_str}")

    lines.append("")
    lines.append("TOP PICKS HARI INI (dengan ramalan probabilistik):")
    for p in picks:
        lines.append(
            f"- {p['symbol']} @ {_format_price(p['price'])} ({p['change_pct']:+.2f}%) | "
            f"Score {p['score']}/100 | {p['action']} | Risk {p['risk']} | "
            f"Alloc {p['alloc_pct']:.1f}% | "
            f"Entry zone {_format_price(p['entry_zone_low'])}–{_format_price(p['entry_zone_high'])} | "
            f"TP1 {_format_price(p['tp1'])} TP2 {_format_price(p['tp2'])} Target {_format_price(p['target'])} SL {_format_price(p['stop_loss'])} | "
            f"Forecast 6h {p['forecast_6h_prob']:.0f}%↑ ({p['forecast_6h_conf']}) "
            f"24h {p['forecast_24h_prob']:.0f}%↑ ({p['forecast_24h_conf']}) | "
            f"Intel {p['intel_confidence']} · Confluence {p['confluence_passed']}/5 · MTF {p['mtf_label']} · {p['regime']}"
        )

    if pf.get("positions"):
        lines.append("")
        lines.append(f"PORTFOLIO USER (modal {_format_idr(pf.get('capital_idr', 0))}):")
        if pf.get("exposure_pct") is not None:
            lines.append(f"- Exposure: {pf['exposure_pct']:.1f}% dari modal · P/L total {pf.get('pnl_pct', 0):+.2f}%")
        for r in pf["positions"]:
            action = r.get("current_action", "—")
            score = r.get("current_score")
            score_str = f"score {score}" if score is not None else "no signal"
            lines.append(
                f"- {r['symbol']}: qty {r['qty']} @ {_format_price(r['avg_buy'])} → sekarang {_format_price(r['current_price'])} "
                f"({r['pnl_pct']:+.2f}%) | sinyal sekarang: {action} ({score_str})"
            )

    lines.append("")
    lines.append("INSTRUKSI OUTPUT (WAJIB ikuti format ini):")
    lines.append("""
🌤 **Outlook Pasar** (1-2 kalimat: kondisi market, mood umum, peringatan kalau ada)

🎯 **Aksi Prioritas Hari Ini** (3-5 bullet, spesifik & actionable):
   - Format: "[Aksi] [Coin] di [zona/harga] dengan alokasi X%, target Y, SL Z"
   - Beri prioritas berdasarkan score + confidence + risk
   - Sebut alasan ringkas (misal: "forecast 6h 70% confidence tinggi + MTF bullish")
   - Kalau tidak ada entry valid, bilang "Tunggu, market belum kasih edge bagus"

💼 **Review Portfolio** (cuma kalau ada posisi):
   - Per posisi: tindakan ringkas (HOLD / TAKE PROFIT / EXIT / DCA)
   - Spesifik: "ETH +3.5% sudah dekat TP1 Rp X, ambil 30% dan geser SL ke breakeven"
   - Kalau ada posisi yang sinyalnya jadi JANGAN BELI/HINDARI: warning untuk exit

⚠️ **Hindari Hari Ini** (kalau relevan):
   - Coin yang risk-nya tinggi atau sinyal lemah
   - Pola yang patut dihindari (FOMO, kejar candle, dll)

📌 **Catatan Penutup** (1 kalimat singkat, bisa motivasional/realistis)

ATURAN:
- Bahasa Indonesia santai tapi profesional
- Jangan pakai jargon berlebihan
- Jangan terlalu optimis — sebut risk dengan jujur
- Maksimum 400 kata total
- WAJIB akhiri dengan "*Bukan saran keuangan. DYOR.*"
""".strip())

    return "\n".join(lines)


def _try_provider(client, model: str, prompt: str) -> tuple[str | None, Exception | None]:
    """Coba panggil satu provider. Return (response_text, None) atau (None, exception)."""
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "Kamu adalah AI Pilot crypto premium. Ringkas, actionable, jujur."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.4,
            max_tokens=900,
        )
        text = resp.choices[0].message.content
        if not text:
            return None, RuntimeError("Empty response")
        return text, None
    except Exception as e:
        return None, e


def _is_quota_error(exc: Exception) -> bool:
    """Cek apakah error karena quota/rate limit (perlu fallback)."""
    name = type(exc).__name__.lower()
    msg = str(exc).lower()
    return (
        "ratelimit" in name
        or "quota" in name
        or "429" in msg
        or "exceeded your current quota" in msg
        or "resource exhausted" in msg
    )


def call_llm_for_playbook(prompt: str, gemini_key: str = "", deepseek_key: str = "") -> str:
    """Panggil LLM dengan auto-fallback. Coba Gemini dulu, kalau quota habis pindah ke Deepseek."""
    if not gemini_key and not deepseek_key:
        return "_AI Auto-Pilot tidak aktif: API key Gemini atau Deepseek belum dipasang._"
    try:
        from openai import OpenAI  # type: ignore
    except ImportError:
        return "_OpenAI client belum terinstall. Jalankan `pip install openai`._"

    errors: list[str] = []

    # Try Gemini first kalau ada
    if gemini_key:
        client = OpenAI(api_key=gemini_key, base_url="https://generativelanguage.googleapis.com/v1beta/openai/")
        text, err = _try_provider(client, "gemini-2.5-flash", prompt)
        if text:
            return text
        if err is not None:
            errors.append(f"Gemini: {type(err).__name__}: {str(err)[:140]}")
            # Kalau bukan quota error & tidak ada deepseek key, langsung return
            if not _is_quota_error(err) and not deepseek_key:
                return f"_Gagal hubungi Gemini: {type(err).__name__}: {str(err)[:200]}_"

    # Fallback ke Deepseek (kalau Gemini gagal dengan quota error, atau Gemini key kosong)
    if deepseek_key:
        client = OpenAI(api_key=deepseek_key, base_url="https://api.deepseek.com")
        text, err = _try_provider(client, "deepseek-chat", prompt)
        if text:
            # Kalau ini fallback dari Gemini, kasih hint
            if errors:
                return f"> ℹ️ _Gemini quota habis, otomatis fallback ke Deepseek_\n\n{text}"
            return text
        if err is not None:
            errors.append(f"Deepseek: {type(err).__name__}: {str(err)[:140]}")

    if errors:
        return "_Semua AI provider gagal:_\n- " + "\n- ".join(errors)
    return "_Tidak ada API key yang valid._"


def generate_playbook(
    market_stats: dict | None,
    top_picks: list[dict],
    portfolio_positions: list[dict] | None,
    portfolio_capital_idr: float,
    news_profile: dict | None,
    learning_profile: dict | None,
    tickers: dict | None,
    gemini_key: str = "",
    deepseek_key: str = "",
) -> dict:
    """High-level entry point. Return {playbook, signature, generated_at}."""
    ctx = build_pilot_context(
        market_stats, top_picks, portfolio_positions,
        portfolio_capital_idr, news_profile, learning_profile, tickers,
    )
    sig = _hash_context(ctx)
    prompt = render_pilot_prompt(ctx)
    playbook = call_llm_for_playbook(prompt, gemini_key, deepseek_key)
    return {
        "playbook": playbook,
        "signature": sig,
        "generated_at": time.time(),
        "context_summary": {
            "n_picks": len(ctx.get("top_picks", [])),
            "n_positions": len(ctx.get("portfolio", {}).get("positions", [])),
            "market_mode": ctx.get("market", {}).get("mode", "normal"),
        },
    }


def generate_signal_insight(coin_data: dict, gemini_key: str = "", deepseek_key: str = "") -> dict:
    """Generate a quick insight for a single realtime signal."""
    prompt = f"""
    Berikan "ANALYTICS & INSIGHT" dan "INSTRUKSI" singkat, padat, dan profesional untuk aset crypto {coin_data.get('symbol')} yang sedang memberikan sinyal {coin_data.get('action')}.
    
    Data aset saat ini:
    Harga: {coin_data.get('price')}
    Perubahan 24j: {coin_data.get('change'):+.2f}%
    RSI: {coin_data.get('rsi')}
    MACD: {coin_data.get('macd_signal')}
    Supertrend: {coin_data.get('supertrend')}
    Machine Learning Forecast: {coin_data.get('ml_label')} ({coin_data.get('ml_prob')}%)
    Score: {coin_data.get('score')}/100
    Risk Level: {coin_data.get('risk_level')}
    
    Tuliskan dalam format ini persis seperti di bawah ini, gunakan Markdown tebal/miring:
    
    📊 *ANALYTICS & INSIGHT:*
    [1 paragraf analisis naratif singkat yang menjelaskan mengapa momentum ini terjadi atau potensinya berdasarkan data teknikal di atas. Gunakan bahasa pro layaknya laporan on-chain/trading profesional]
    
    🟢 *INSTRUKSI:*
    [1-2 kalimat instruksi trading konkrit terkait titik entry, trailing, atau take profit]
    
    Batasi maksimal 70 kata secara keseluruhan. Jangan beri salam pembuka/penutup.
    """
    
    insight_text = call_llm_for_playbook(prompt, gemini_key, deepseek_key)
    
    # Clean up
    insight_text = insight_text.replace("```markdown", "").replace("```", "").strip()
    if "_Semua AI provider gagal" in insight_text or "_Tidak ada API" in insight_text:
        insight_text = "📊 *ANALYTICS & INSIGHT:*\nAI Insight tidak tersedia saat ini.\n\n🟢 *INSTRUKSI:*\nIkuti sinyal teknikal di atas dengan manajemen risiko."
        
    return {"insight": insight_text}


def generate_custom_explain(coin_data: dict, gemini_key: str = "", deepseek_key: str = "") -> str:
    """Generate a premium, comprehensive AI analysis for a single coin requested by the user."""
    price_str = _format_price(coin_data.get("price", 0))
    tp1_str = _format_price(coin_data.get("tp1", 0)) if coin_data.get("tp1") else "-"
    tp2_str = _format_price(coin_data.get("tp2", 0)) if coin_data.get("tp2") else "-"
    sl_str = _format_price(coin_data.get("stop_loss", 0)) if coin_data.get("stop_loss") else "-"
    
    prompt = f"""
    Bertindaklah sebagai AI Crypto Analyst Senior. Berikan analisis mendalam, obyektif, dan profesional untuk aset crypto {coin_data.get('symbol')} berdasarkan data teknikal dan analisis pasar terkini.

    DATA TEKNIKAL {coin_data.get('symbol')}:
    - Harga Saat Ini: {price_str}
    - Perubahan 24 Jam: {coin_data.get('change'):+.2f}%
    - RSI (14): {coin_data.get('rsi')}
    - MACD Signal: {coin_data.get('macd_signal')}
    - Supertrend: {coin_data.get('supertrend')}
    - Multi-Timeframe Confirmation (MTF): {coin_data.get('mtf_label')}
    - Rekomendasi Bot: {coin_data.get('action')} (Score: {coin_data.get('score')}/100)
    - Machine Learning Forecast: {coin_data.get('ml_label')} ({coin_data.get('ml_prob')}%)
    """
    
    if coin_data.get('action') in ("BELI KUAT", "CICIL BELI"):
        prompt += f"""
    - Target Profit 1 (TP1): {tp1_str}
    - Target Profit 2 (TP2): {tp2_str}
    - Stop Loss (SL): {sl_str}
    - Alokasi Modal Direkomendasikan: {coin_data.get('alloc_pct')}%
    """
    
    prompt += f"""
    Tuliskan laporan analisis dalam bahasa Indonesia dengan struktur Markdown premium berikut:

    🔍 **Analisis Momentum & Trend:**
    [Analisis mendalam mengenai kondisi trend saat ini berdasarkan RSI, MACD, Supertrend, dan MTF. Apakah jenuh beli/jenuh jual? Apakah trend bullish/bearish kuat?]

    🧠 **Prediksi Machine Learning & Sentimen:**
    [Jelaskan pandangan AI/ML forecast ({coin_data.get('ml_label')}) dan signifikansi probabilitasnya ({coin_data.get('ml_prob')}%) dalam market saat ini. Hubungkan dengan sentiment pasar jika relevan.]

    🛡️ **Rekomendasi Strategi & Manajemen Risiko:**
    [Berikan panduan taktis bagi trader: apakah layak masuk sekarang, menunggu (wait & see), atau keluar/hindari. Jika layak masuk, bagaimana skenario TP/SL dan alokasi terbaik. Jika tidak, sebutkan level konfirmasi yang harus ditunggu.]

    BATASAN:
    - Gunakan bahasa Indonesia yang profesional, berwawasan, dan tidak bertele-tele.
    - Jangan memberikan kepastian mutlak (gunakan probabilitas).
    - Maksimal 150 kata secara keseluruhan.
    - WAJIB akhiri dengan "*Bukan saran keuangan. DYOR.*"
    """
    
    analysis = call_llm_for_playbook(prompt, gemini_key, deepseek_key)
    analysis = analysis.replace("```markdown", "").replace("```", "").strip()
    
    if "_Semua AI provider gagal" in analysis or "_Tidak ada API" in analysis:
        analysis = (
            f"🔍 *Analisis Momentum & Trend:*\nTidak dapat menghubungi provider AI untuk analisis saat ini.\n\n"
            f"🧠 *Prediksi Machine Learning & Sentimen:*\nForecast: {coin_data.get('ml_label')} ({coin_data.get('ml_prob')}%)\n\n"
            f"🛡️ *Rekomendasi Strategi & Manajemen Risiko:*\nBot Action: {coin_data.get('action')} (Score: {coin_data.get('score')}/100)."
        )
    return analysis


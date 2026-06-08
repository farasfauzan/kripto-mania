import json
import os
import time
from datetime import datetime
from core.applog import get_logger
from core.indodax_trade import sell_market

logger = get_logger("portfolio_manager")

PORTFOLIO_FILE = "active_trades.json"

def _load_portfolio() -> dict:
    if os.path.exists(PORTFOLIO_FILE):
        try:
            with open(PORTFOLIO_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load portfolio: {e}")
    return {}

def _save_portfolio(data: dict):
    try:
        with open(PORTFOLIO_FILE, "w") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        logger.error(f"Failed to save portfolio: {e}")

def save_position(symbol: str, buy_price: float, amount_coin: float, tp1: float, tp2: float, sl: float, trade_type: str = "EARLY"):
    """Mencatat posisi baru yang baru saja dibeli.
    
    Args:
        symbol: 'btc', 'doge' dll.
        buy_price: Harga beli rata-rata.
        amount_coin: Jumlah koin yang dipegang.
        tp1, tp2, sl: Target profit dan stop loss.
        trade_type: "EARLY" atau "KUAT"
    """
    portfolio = _load_portfolio()
    
    # Jika sudah punya posisi di koin yang sama, gabungkan jumlahnya dan rata-rata harganya (Average Down/Up)
    # Untuk simpelnya sekarang, kita timpa saja dengan harga rata-rata baru.
    if symbol in portfolio:
        old = portfolio[symbol]
        total_coin = old["amount_coin"] + amount_coin
        avg_price = ((old["buy_price"] * old["amount_coin"]) + (buy_price * amount_coin)) / total_coin
        logger.info(f"Adding position to {symbol.upper()}. New Avg: {avg_price:.0f}, Total Coin: {total_coin}")
        amount_coin = total_coin
        buy_price = avg_price
        
    portfolio[symbol] = {
        "buy_price": buy_price,
        "amount_coin": amount_coin,
        "tp1": tp1,
        "tp2": tp2,
        "sl": sl,
        "trade_type": trade_type,
        "timestamp": datetime.now().isoformat(),
        "highest_price": buy_price # Untuk trailing stop loss
    }
    _save_portfolio(portfolio)
    logger.info(f"Posisi disimpan: {symbol.upper()} | Beli: {buy_price:,.0f} | SL: {sl:,.0f} | TP1: {tp1:,.0f}")

def remove_position(symbol: str):
    """Menghapus posisi dari catatan (setelah dijual)."""
    portfolio = _load_portfolio()
    if symbol in portfolio:
        del portfolio[symbol]
        _save_portfolio(portfolio)
        logger.info(f"Posisi {symbol.upper()} dihapus dari portofolio.")

def check_tp_sl(current_prices: dict) -> list:
    """Mengecek semua posisi aktif terhadap harga saat ini.
    Jika ada yang kena TP atau SL, langsung JUAL otomatis.
    
    Args:
        current_prices: dict {symbol: current_price_float}
        
    Returns:
        list of dict berisi laporan penjualan untuk dikirim ke Telegram.
    """
    portfolio = _load_portfolio()
    reports = []
    
    for symbol, pos in list(portfolio.items()):
        if symbol not in current_prices:
            continue
            
        curr_price = current_prices[symbol]
        buy_price = pos["buy_price"]
        amount = pos["amount_coin"]
        sl = pos["sl"]
        tp1 = pos["tp1"]
        tp2 = pos["tp2"]
        highest = pos.get("highest_price", buy_price)
        
        # Update trailing high
        if curr_price > highest:
            pos["highest_price"] = curr_price
            _save_portfolio(portfolio)
            highest = curr_price
            
        reason = ""
        action = False
        
        # Hitung PnL
        pnl_pct = (curr_price - buy_price) / buy_price * 100
        
        # 1. Cek Stop Loss (Cutloss)
        if curr_price <= sl:
            reason = f"🛑 STOP LOSS TERSENTUH (-{abs(pnl_pct):.2f}%)"
            action = True
            
        # 2. Cek Take Profit 2 (All Out)
        elif curr_price >= tp2:
            reason = f"🎯 TAKE PROFIT 2 TERSENTUH (+{pnl_pct:.2f}%)"
            action = True
            
        # 3. Cek Trailing Stop / TP1 (Sederhana: Kalau sudah lewat TP1, dan turun X% dari highest)
        # Trailing stop aktif jika harga sudah minimal naik 2%
        elif pnl_pct > 2.0:
            trailing_drop = (highest - curr_price) / highest * 100
            if trailing_drop >= 2.5:  # Jika turun 2.5% dari pucuk tertinggi
                reason = f"🛡️ TRAILING STOP AKTIF (+{pnl_pct:.2f}%)"
                action = True
                
        if action:
            logger.info(f"Eksekusi Jual Otomatis {symbol.upper()}: {reason} di harga {curr_price:,.0f}")
            res = sell_market(symbol, amount)
            
            if res.get("success"):
                remove_position(symbol)
                received_idr = res.get("received_idr", 0)
                spent_idr = buy_price * amount
                profit_idr = received_idr - spent_idr
                
                reports.append({
                    "symbol": symbol.upper(),
                    "reason": reason,
                    "sell_price": res.get("avg_price", curr_price),
                    "buy_price": buy_price,
                    "profit_pct": pnl_pct,
                    "profit_idr": profit_idr
                })
            else:
                logger.error(f"Gagal mengeksekusi Auto-Sell {symbol.upper()}: {res.get('error')}")
                # Jangan hapus posisi dari portfolio agar di loop berikutnya dicoba lagi.
                
    return reports

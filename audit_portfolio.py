import time
from core.indodax_trade import get_balance, sell_market
from core.portfolio_manager import save_position
from telegram_bot import fetch_all_tickers, apply_bot_intelligence, analyze_coin
from core.indicators import fetch_candles

def audit_porto():
    print("="*50)
    print("🔍 PRO TRADER AUDIT: MEMBERSIHKAN PORTOFOLIO 🔍")
    print("="*50)
    
    balances = get_balance()
    if not balances:
        print("Gagal mengambil saldo dari Indodax. Pastikan API Key benar.")
        return
        
    tickers = fetch_all_tickers()
    if not tickers:
        print("Gagal mengambil data market Indodax.")
        return
        
    print(f"Saldo IDR awal: Rp {balances.get('idr', 0):,.0f}\n")
    
    for coin, amount in balances.items():
        if coin == 'idr' or amount <= 0:
            continue
            
        ticker_data = tickers.get(coin.upper())
        if not ticker_data:
            continue
            
        # Asumsikan batas minimal jual di Indodax adalah Rp 10.000.
        # Jika nilai koin < Rp 10.000, kemungkinan akan gagal dijual (Minimum Transaction)
        curr_price = float(ticker_data.get('price', 0))
        est_value = amount * curr_price
        
        print(f"--- Menganalisis {coin.upper()} ---")
        print(f"Jumlah: {amount} | Estimasi Nilai: Rp {est_value:,.0f}")
        
        if est_value < 10000:
            print(f"⏭️ Di-skip karena nilainya di bawah minimum jual Indodax (Rp 10.000).\n")
            continue
            
        # Fetch candles 1h untuk analisis
        candles = fetch_candles(f"{coin}_idr", "60", lookback_days=10)
        if candles is None or candles.empty:
            print(f"❌ Gagal fetch grafik untuk {coin}\n")
            continue
            
        res = apply_bot_intelligence(analyze_coin(coin.upper(), ticker_data, candles))
        
        print(f"Skor AI: {res['score']}/100 | Status: {res['action']} | ML: {res['ml_label']}")
        
        if res["action"] in ["JANGAN BELI", "HINDARI"]:
            print(f"⚠️ TREN BURUK! Menjual paksa (Liquidate) {coin.upper()} untuk selamatkan dana...")
            sell_res = sell_market(coin, amount, curr_price)
            if sell_res.get("success"):
                print(f"✅ SUKSES JUAL! Mendapat Rp {sell_res['received_idr']:,.0f}")
            else:
                print(f"❌ GAGAL JUAL: {sell_res.get('error')}")
        else:
            print(f"🛡️ TREN AMAN! Koin ini akan ditahan (Hold) dan dikawal oleh Trailing Stop.")
            # Karena kita tidak tahu harga beli asli masa lalu, kita anggap "Harga Beli" adalah harga saat ini.
            # Jadi TP/SL akan dihitung dari harga sekarang.
            save_position(
                symbol=coin,
                buy_price=curr_price,
                amount_coin=amount,
                tp1=res["tp1"],
                tp2=res["tp2"],
                sl=res["stop_loss"],
                trade_type="AUDIT HOLD"
            )
        print("\n")
        
    print("="*50)
    print("✅ AUDIT SELESAI")
    new_balances = get_balance()
    print(f"Saldo IDR Akhir Anda: Rp {new_balances.get('idr', 0):,.0f}")
    print("="*50)

if __name__ == "__main__":
    audit_porto()

import time
import urllib.parse
import hmac
import hashlib
import requests
import logging
import os
from core.applog import get_logger

logger = get_logger("indodax_trade")

# API Base URL
INDODAX_API_URL = "https://indodax.com/tapi"

def _get_api_keys():
    api_key = os.environ.get("INDODAX_API_KEY", "")
    secret_key = os.environ.get("INDODAX_SECRET_KEY", "")
    if not api_key or not secret_key:
        try:
            import streamlit as st
            api_key = st.secrets.get("INDODAX_API_KEY", "")
            secret_key = st.secrets.get("INDODAX_SECRET_KEY", "")
        except Exception:
            pass
    return api_key, secret_key

def _build_headers(post_data: str, secret_key: str, api_key: str) -> dict:
    sign = hmac.new(
        secret_key.encode("utf-8"),
        post_data.encode("utf-8"),
        hashlib.sha512
    ).hexdigest()
    return {
        "Key": api_key,
        "Sign": sign,
        "Content-Type": "application/x-www-form-urlencoded"
    }

def _send_request(data: dict) -> dict:
    api_key, secret_key = _get_api_keys()
    if not api_key or not secret_key:
        logger.error("Indodax API keys not configured.")
        return {"success": 0, "error": "Keys not configured"}

    # Selalu inject nonce terbaru
    data["nonce"] = int(time.time() * 1000)
    post_data = urllib.parse.urlencode(data)
    headers = _build_headers(post_data, secret_key, api_key)

    try:
        r = requests.post(INDODAX_API_URL, headers=headers, data=post_data, timeout=10)
        res = r.json()
        if res.get("success") == 0:
            logger.error(f"API Error ({data.get('method')}): {res.get('error')}")
        return res
    except Exception as e:
        logger.error(f"API Request Failed: {e}")
        return {"success": 0, "error": str(e)}

def get_balance() -> dict:
    """Mengambil saldo rupiah dan aset lainnya.
    Returns:
        {
            "idr": float,
            "btc": float,
            ...
        }
    """
    res = _send_request({"method": "getInfo"})
    if res.get("success") == 1:
        # returns dict of {coin: balance_float}
        balances = res.get("return", {}).get("balance", {})
        return {k: float(v) for k, v in balances.items()}
    return {}

def get_idr_balance() -> float:
    return get_balance().get("idr", 0.0)

def buy_market(symbol: str, idr_amount: float, price: float) -> dict:
    """Eksekusi Beli Market (emulasi dengan limit price tinggi)
    
    Args:
        symbol: e.g. 'btc' (tanpa _idr)
        idr_amount: Jumlah rupiah yang mau dibelikan
        price: Harga current. Order dikirim sedikit lebih mahal agar instan.
    """
    buy_price_limit = int(price * 1.05)  # +5% agar di-match instan
    logger.info(f"Mencoba Beli {symbol.upper()} senilai Rp{idr_amount:,.0f} di limit Rp{buy_price_limit}...")
    pair = f"{symbol.lower()}_idr"
    data = {
        "method": "trade",
        "pair": pair,
        "type": "buy",
        "price": str(buy_price_limit),
        "rupiah": str(int(idr_amount)),
    }
    res = _send_request(data)
    
    if res.get("success") == 1:
        # Ambil harga beli efektif dari data history order
        received = float(res.get("return", {}).get("receive_coin", 0))
        remains_idr = float(res.get("return", {}).get("remains_rupiah", 0))
        spent_idr = idr_amount - remains_idr
        avg_price = spent_idr / received if received > 0 else 0
        order_id = res.get("return", {}).get("order_id", 0)
        
        logger.info(f"✅ Beli Sukses! Dapat {received} {symbol.upper()} (Harga Rata-rata: Rp{avg_price:,.0f})")
        return {
            "success": True,
            "order_id": order_id,
            "received_coin": received,
            "spent_idr": spent_idr,
            "avg_price": avg_price
        }
    else:
        logger.error(f"❌ Beli Gagal: {res.get('error')}")
        return {
            "success": False,
            "error": res.get("error")
        }

def sell_market(symbol: str, coin_amount: float, price: float) -> dict:
    """Eksekusi Jual Market (emulasi dengan limit price rendah)
    
    Args:
        symbol: e.g. 'btc'
        coin_amount: Jumlah koin yang mau dijual
        price: Harga saat ini (untuk mematok batas bawah).
    """
    sell_price_limit = int(price * 0.90) if price > 2 else 1  # -10% agar di-match instan, min 1
    
    # Format amount to avoid 'decimal' error for integers (e.g. 70996.0 -> 70996)
    amt_str = f"{coin_amount:.8f}".rstrip('0').rstrip('.')
    if '.' not in amt_str and amt_str == '': amt_str = '0'

    logger.info(f"Mencoba Jual {amt_str} {symbol.upper()} di limit Rp{sell_price_limit}...")
    pair = f"{symbol.lower()}_idr"
    data = {
        "method": "trade",
        "pair": pair,
        "type": "sell",
        "price": str(sell_price_limit),
        f"{symbol.lower()}": amt_str,  # Indodax API rule
    }
    res = _send_request(data)
    
    if res.get("success") == 1:
        received_idr = float(res.get("return", {}).get("receive_rupiah", 0))
        remains_coin = float(res.get("return", {}).get(f"remains_{symbol.lower()}", 0))
        sold_coin = coin_amount - remains_coin
        avg_price = received_idr / sold_coin if sold_coin > 0 else 0
        order_id = res.get("return", {}).get("order_id", 0)
        
        logger.info(f"✅ Jual Sukses! Dapat Rp{received_idr:,.0f} (Harga Rata-rata: Rp{avg_price:,.0f})")
        return {
            "success": True,
            "order_id": order_id,
            "sold_coin": sold_coin,
            "received_idr": received_idr,
            "avg_price": avg_price
        }
    else:
        logger.error(f"❌ Jual Gagal: {res.get('error')}")
        return {
            "success": False,
            "error": res.get("error")
        }

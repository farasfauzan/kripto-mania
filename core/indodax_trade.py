import time
import urllib.parse
import hmac
import hashlib
import requests
import logging
import os
import threading
from core.applog import get_logger

logger = get_logger("indodax_trade")

_last_request_lock = threading.Lock()
_last_request_time = 0.0

# API Base URL
INDODAX_API_URL = "https://indodax.com/tapi"

def _submission_unknown(error) -> dict:
    return {
        "success": False,
        "submission_status": "UNKNOWN",
        "manual_reconciliation_required": True,
        "error": str(error),
    }

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
    global _last_request_time
    api_key, secret_key = _get_api_keys()
    if not api_key or not secret_key:
        logger.error("Indodax API keys not configured.")
        return {"success": 0, "error": "Keys not configured"}

    # Enforce minimum 350ms delay between API requests (max ~170 requests per minute)
    with _last_request_lock:
        now = time.time()
        elapsed = now - _last_request_time
        if elapsed < 0.35:
            time.sleep(0.35 - elapsed)
        _last_request_time = time.time()

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
        return _submission_unknown(e)

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

def cancel_order(symbol: str, order_id: int, order_type: str) -> dict:
    """Membatalkan order yang masih menggantung."""
    pair = f"{symbol.lower()}_idr"
    data = {
        "method": "cancelOrder",
        "pair": pair,
        "order_id": str(order_id),
        "type": order_type,
    }
    return _send_request(data)

def get_order(symbol: str, order_id: int) -> dict:
    """Mengambil status detail sebuah order."""
    pair = f"{symbol.lower()}_idr"
    data = {
        "method": "getOrder",
        "pair": pair,
        "order_id": str(order_id),
    }
    return _send_request(data)

def buy_market(symbol: str, idr_amount: float, price: float) -> dict:
    """Eksekusi Beli Market dengan emulasi Limit Tinggi + Instan Cancel sisa.
    
    1. Kirim order limit +5% dari harga saat ini.
    2. Tunggu 1 detik.
    3. Batalkan sisa order yang belum keisi.
    4. Ambil data order final dari getOrder untuk mencatat jumlah aktual.
    """
    buy_price_limit = int(price * 1.05)
    logger.info(f"Mencoba Beli {symbol.upper()} senilai Rp{idr_amount:,.0f} di limit Rp{buy_price_limit}...")
    pair = f"{symbol.lower()}_idr"
    data = {
        "method": "trade",
        "pair": pair,
        "type": "buy",
        "price": str(buy_price_limit),
        "idr": str(int(idr_amount)),
    }
    res = _send_request(data)

    if res.get("submission_status") == "UNKNOWN":
        logger.error(f"Status beli {symbol.upper()} tidak diketahui; rekonsiliasi manual diperlukan.")
        return dict(res)
    
    if res.get("success") == 1:
        order_id = res.get("return", {}).get("order_id", 0)
        if not order_id:
            logger.error("Beli gagal: No order_id returned in success response.")
            return {"success": False, "error": "No order_id returned"}

        # Tunggu 1 detik agar matching engine Indodax memproses order instan
        time.sleep(1.0)

        # Batalkan sisa order yang tidak keisi (jika ada)
        cancel_order(symbol, order_id, "buy")
        
        # Ambil data final terisi dari getOrder
        order_detail_res = get_order(symbol, order_id)
        if order_detail_res.get("success") == 1:
            order_info = order_detail_res.get("return", {}).get("order", {})
            
            # Cari key dinamis untuk receive coin, misal receive_btc, receive_cst, dll
            coin_key = f"receive_{symbol.lower()}"
            received = float(order_info.get(coin_key, 0))
            
            order_rp = float(order_info.get("order_rp", idr_amount))
            remain_rp = float(order_info.get("remain_rp", 0))
            spent_idr = order_rp - remain_rp
            avg_price = spent_idr / received if received > 0 else 0.0

            if received <= 0:
                logger.warning(f"⚠️ Beli gagal fill sama sekali untuk {symbol.upper()} (Order ID: {order_id})")
                return {
                    "success": False,
                    "error": "Order completely unfilled"
                }

            logger.info(f"✅ Beli Sukses! Terisi: {received} {symbol.upper()} | Habis: Rp{spent_idr:,.0f} | Harga Rata-rata: Rp{avg_price:,.0f}")
            return {
                "success": True,
                "order_id": order_id,
                "received_coin": received,
                "spent_idr": spent_idr,
                "avg_price": avg_price
            }
        else:
            # Fallback jika getOrder gagal
            logger.warning("Gagal fetch getOrder detail; menggunakan estimasi dari response trade awal.")
            received = float(res.get("return", {}).get(f"receive_{symbol.lower()}", 0))
            remain_rp = float(res.get("return", {}).get("remain_rp", 0))
            spent_idr = idr_amount - remain_rp
            avg_price = spent_idr / received if received > 0 else 0.0
            return {
                "success": received > 0,
                "order_id": order_id,
                "received_coin": received,
                "spent_idr": spent_idr,
                "avg_price": avg_price,
                "error": "Failed to get order details after cancel" if received <= 0 else None
            }
    else:
        logger.error(f"❌ Beli Gagal: {res.get('error')}")
        return {
            "success": False,
            "error": res.get("error")
        }

def sell_market(symbol: str, coin_amount: float, price: float) -> dict:
    """Eksekusi Jual Market dengan emulasi Limit Rendah + Instan Cancel sisa.
    
    1. Kirim order limit -10% dari harga saat ini.
    2. Tunggu 1 detik.
    3. Batalkan sisa order yang belum keisi.
    4. Ambil data order final dari getOrder untuk mencatat jumlah aktual.
    """
    sell_price_limit = int(price * 0.90) if price > 2 else 1
    amt_str = f"{coin_amount:.8f}".rstrip('0').rstrip('.')
    if '.' not in amt_str and amt_str == '': amt_str = '0'

    logger.info(f"Mencoba Jual {amt_str} {symbol.upper()} di limit Rp{sell_price_limit}...")
    pair = f"{symbol.lower()}_idr"
    data = {
        "method": "trade",
        "pair": pair,
        "type": "sell",
        "price": str(sell_price_limit),
        f"{symbol.lower()}": amt_str,
    }
    res = _send_request(data)

    if res.get("submission_status") == "UNKNOWN":
        logger.error(f"Status jual {symbol.upper()} tidak diketahui; rekonsiliasi manual diperlukan.")
        return dict(res)
    
    if res.get("success") == 1:
        order_id = res.get("return", {}).get("order_id", 0)
        if not order_id:
            logger.error("Jual gagal: No order_id returned in success response.")
            return {"success": False, "error": "No order_id returned"}

        # Tunggu 1 detik agar matching engine Indodax memproses order instan
        time.sleep(1.0)

        # Batalkan sisa order yang tidak keisi
        cancel_order(symbol, order_id, "sell")
        
        # Ambil data final terisi dari getOrder
        order_detail_res = get_order(symbol, order_id)
        if order_detail_res.get("success") == 1:
            order_info = order_detail_res.get("return", {}).get("order", {})
            
            # Hitung koin terjual riil dari order_coin - remain_coin
            coin_key = symbol.lower()
            order_coin = float(order_info.get(f"order_{coin_key}", coin_amount))
            remain_coin = float(order_info.get(f"remain_{coin_key}", 0))
            sold_coin = order_coin - remain_coin
            
            received_idr = float(order_info.get("receive_rp", 0))
            avg_price = received_idr / sold_coin if sold_coin > 0 else 0.0

            if sold_coin <= 0:
                logger.warning(f"⚠️ Jual gagal fill sama sekali untuk {symbol.upper()} (Order ID: {order_id})")
                return {
                    "success": False,
                    "error": "Order completely unfilled"
                }

            logger.info(f"✅ Jual Sukses! Terjual: {sold_coin} {symbol.upper()} | Dapat: Rp{received_idr:,.0f} | Harga Rata-rata: Rp{avg_price:,.0f}")
            return {
                "success": True,
                "order_id": order_id,
                "sold_coin": sold_coin,
                "received_idr": received_idr,
                "avg_price": avg_price
            }
        else:
            # Fallback jika getOrder gagal
            logger.warning("Gagal fetch getOrder detail; menggunakan estimasi dari response trade awal.")
            remain_coin = float(res.get("return", {}).get(f"remain_{symbol.lower()}", 0))
            sold_coin = coin_amount - remain_coin
            received_idr = float(res.get("return", {}).get("receive_rp", 0))
            avg_price = received_idr / sold_coin if sold_coin > 0 else 0.0
            return {
                "success": sold_coin > 0,
                "order_id": order_id,
                "sold_coin": sold_coin,
                "received_idr": received_idr,
                "avg_price": avg_price,
                "error": "Failed to get order details after cancel" if sold_coin <= 0 else None
            }
    else:
        logger.error(f"❌ Jual Gagal: {res.get('error')}")
        return {
            "success": False,
            "error": res.get("error")
        }

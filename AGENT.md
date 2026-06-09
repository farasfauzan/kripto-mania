# AGENTS.md

## Project Goal
Kripto Mania adalah AI Crypto Portfolio Manager pribadi untuk crypto spot trading.
Prioritas utama adalah safety, risk management, dan paper trading sebelum real auto-trade.

## Hard Rules
- Jangan melakukan real trade saat development/testing.
- Jangan memanggil API Indodax sungguhan saat test.
- Jangan hardcode API key, token, secret, atau credential.
- AUTO_TRADE_ENABLED harus default false.
- PAPER_TRADING_MODE harus default true.
- CONFIRM_BEFORE_TRADE harus default true.
- LLM/AI advisor tidak boleh langsung mengeksekusi order.
- Semua real order harus melewati execution_engine dan risk_manager.
- Jangan rewrite total app.py kecuali benar-benar perlu.
- Jangan menghapus fitur lama tanpa alasan kuat.

## Required Checks
Jalankan setelah perubahan:
python -m py_compile app.py telegram_bot.py core/indodax_trade.py core/portfolio_manager.py learning_engine.py journal_store.py
python test_learning.py

Jika menambah pytest:
pytest

## Development Strategy
Kerjakan bertahap:
1. Safety patch
2. Paper trading
3. Risk manager
4. Telegram confirmation
5. Portfolio allocator
6. ML ensemble
7. Dashboard portfolio
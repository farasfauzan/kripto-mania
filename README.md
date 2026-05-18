---
title: Kripto Mania
emoji: 🤖
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
---

# Kripto Mania - Bot Trading Cerdas Indodax 24/7

Bot daemon Telegram cerdas yang memantau pasar Indodax menggunakan indikator teknikal (RSI, EMA, MACD, Bollinger Bands, Supertrend, ADX), ML/KNN, dan backtesting historis.

## Secrets

Set secrets berikut di Hugging Face Space Settings sebelum menjalankan bot:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `DEEPSEEK_API_KEY` jika fitur AI Advisor digunakan

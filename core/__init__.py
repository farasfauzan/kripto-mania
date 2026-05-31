"""Core shared logic for Kripto Mania.

Modul ini adalah SATU-SATUNYA sumber kebenaran untuk indikator teknikal,
analisis sinyal, dan fetch candle — dipakai bersama oleh web (app.py) dan
daemon Telegram (telegram_bot.py). Tujuannya: web & bot tidak akan pernah
memberi sinyal yang bertentangan untuk koin yang sama.
"""

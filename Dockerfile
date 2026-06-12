FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN apt-get update && apt-get install -y libgomp1 curl ca-certificates && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Hugging Face Spaces requires port 7860
ENV PORT=7860
ENV KEEP_ALIVE_PORT=8080
ENV PYTHONUNBUFFERED=1

EXPOSE 7860

# Run bot daemon in background (auto-restart kalau crash), Streamlit di foreground.
# Loop restart penting di HF Spaces: kalau bot crash, Space tetap "Running" karena
# yang dipantau cuma streamlit — tanpa loop ini bot bisa mati diam-diam.
CMD ["sh", "-c", "(while true; do echo '[boot] starting telegram_bot.py'; python telegram_bot.py; echo '[boot] telegram_bot.py exited, restart in 10s'; sleep 10; done) & exec streamlit run app.py --server.port 7860 --server.address 0.0.0.0"]


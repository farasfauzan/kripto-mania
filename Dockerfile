FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Hugging Face Spaces requires port 7860
ENV PORT=7860
ENV KEEP_ALIVE_PORT=8080
ENV PYTHONUNBUFFERED=1

EXPOSE 7860

# Run bot daemon in background, and Streamlit app in foreground
CMD ["sh", "-c", "python telegram_bot.py & exec streamlit run app.py --server.port 7860 --server.address 0.0.0.0"]

FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Streamlit default port is 8501, but Cloud Run uses 8080
ENV PORT=8080

EXPOSE 8080

ENTRYPOINT ["python", "telegram_bot.py"]

FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Hugging Face Spaces requires port 7860
ENV PORT=7860
ENV PYTHONUNBUFFERED=1

EXPOSE 7860

ENTRYPOINT ["python", "telegram_bot.py"]

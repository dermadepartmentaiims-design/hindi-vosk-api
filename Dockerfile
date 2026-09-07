FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY languages.json .
COPY models ./models

ENV PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "python -m uvicorn app:app --host 0.0.0.0 --port ${PORT}"]

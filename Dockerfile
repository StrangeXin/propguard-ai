FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends gcc && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt 2>&1

COPY backend/app/ app/
COPY data/ /app/data/

CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8001}

# ParcelPilot API — build from repo root:
#   docker build -f apps/api/Dockerfile -t parcelpilot-api .
#   docker run --env-file apps/api/.env -p 8000:8000 -v chroma:/data/chroma parcelpilot-api

FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DATA_PATH=./Data \
    CHROMA_PATH=/data/chroma

WORKDIR /app

# System deps for psycopg2 / chroma
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY apps/api/requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY apps/api/ .
COPY Data/ ./Data/

RUN sed -i 's/\r$//' /app/docker-entrypoint.sh \
    && chmod +x /app/docker-entrypoint.sh \
    && mkdir -p /data/chroma

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/health || exit 1

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

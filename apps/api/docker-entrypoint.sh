#!/bin/sh
set -e

# Optional one-shot bootstrap (set RUN_INGEST=1 on first deploy)
if [ "${RUN_INGEST:-0}" = "1" ]; then
  echo "[entrypoint] Loading Excel → Postgres..."
  python -m app.ingest
fi

if [ "${RUN_CHROMA_INGEST:-0}" = "1" ]; then
  echo "[entrypoint] Building Chroma index (PDFs + Gemini)..."
  python -m app.ingest.chroma
fi

exec "$@"

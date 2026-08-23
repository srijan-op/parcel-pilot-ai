# Docker / EC2 deploy

Build **from the repository root** so the API image can copy `Data/`.

## Images

| Service | Dockerfile | Port |
|---------|------------|------|
| API | `apps/api/Dockerfile` | 8000 |
| Web | `apps/web/Dockerfile` | 3000 |

## Quick start (same machine / EC2)

1. Create `apps/api/.env` from `.env.example` (Groq, Gemini, `DATABASE_URL`, etc.).
2. Set CORS to your public web URL, e.g. `CORS_ORIGINS=http://YOUR_ELASTIC_IP:3000`.
3. Export the browser-facing API URL (rebuild web after any change):

```bash
export NEXT_PUBLIC_API_URL=http://YOUR_ELASTIC_IP:8000
```

4. First boot — load Postgres + Chroma:

```bash
RUN_INGEST=1 RUN_CHROMA_INGEST=1 docker compose up -d --build
```

5. Later boots (reuse `chroma_data` volume):

```bash
docker compose up -d --build
```

6. Open `http://YOUR_ELASTIC_IP:3000` — API health: `http://YOUR_ELASTIC_IP:8000/health`.

EC2 security group: allow inbound **22**, **3000**, **8000**.

## Build images separately

```bash
# API
docker build -f apps/api/Dockerfile -t parcelpilot-api .

docker run --env-file apps/api/.env \
  -e RUN_INGEST=1 -e RUN_CHROMA_INGEST=1 \
  -p 8000:8000 -v chroma_data:/data/chroma \
  parcelpilot-api

# Web (API URL is fixed at build time)
docker build -f apps/web/Dockerfile \
  --build-arg NEXT_PUBLIC_API_URL=http://YOUR_ELASTIC_IP:8000 \
  -t parcelpilot-web .

docker run -p 3000:3000 parcelpilot-web
```

## Notes

- `NEXT_PUBLIC_API_URL` is baked into the Next.js client at **build** time — rebuild the web image if the Elastic IP / domain changes.
- Chroma lives in Docker volume `chroma_data` (`CHROMA_PATH=/data/chroma`).
- Postgres stays on Supabase (or any `DATABASE_URL`); it is not containerized here.
- After HITL demos mutate tickets, reset with `RUN_INGEST=1` once (or `docker compose run --rm -e RUN_INGEST=1 api`).

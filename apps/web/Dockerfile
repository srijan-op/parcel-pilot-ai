# Pin Alpine 3.21 for current security patches (avoid floating node:20-alpine).
ARG NODE_IMAGE=node:20-alpine3.21

FROM ${NODE_IMAGE} AS deps
WORKDIR /app
COPY apps/web/package.json apps/web/package-lock.json* ./
RUN apk upgrade --no-cache \
    && npm ci

FROM ${NODE_IMAGE} AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY apps/web/ .

ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL

RUN apk upgrade --no-cache \
    && npm run build

# Minimal runtime — no Alpine shell/npm in the final image
FROM gcr.io/distroless/nodejs20-debian12 AS runner
WORKDIR /app
ENV NODE_ENV=production \
    PORT=3000 \
    HOSTNAME=0.0.0.0

COPY --from=builder /app/public ./public
COPY --from=builder --chown=nonroot:nonroot /app/.next/standalone ./
COPY --from=builder --chown=nonroot:nonroot /app/.next/static ./.next/static

EXPOSE 3000
CMD ["server.js"]
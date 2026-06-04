# frontend/Dockerfile
# Next.js 16 frontend — multi-stage build producing a small standalone image.
# Requires `output: "standalone"` in next.config.ts (see the patch in chat).

# ---- Stage 1: install deps ----
FROM node:20-slim AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci

# ---- Stage 2: build ----
FROM node:20-slim AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# Build-time public base URL — baked into the client bundle by Next.js.
# Passed in via `az acr build --build-arg NEXT_PUBLIC_BASE_URL=...`.
ARG NEXT_PUBLIC_BASE_URL
ENV NEXT_PUBLIC_BASE_URL=$NEXT_PUBLIC_BASE_URL
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

# ---- Stage 3: runtime (small) ----
FROM node:20-slim AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

# Standalone output bundles only what's needed to run.
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public

EXPOSE 3000
# server.js is produced by Next.js standalone output.
CMD ["node", "server.js"]

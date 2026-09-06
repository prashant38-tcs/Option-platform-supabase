# Frontend Dockerfile -- Next.js dashboard, multi-stage standalone build.
# Portable across PaaS providers (Railway, Render, etc.) -- see backend
# Dockerfile comment re: PORT env var handling, which Next.js standalone's
# generated server.js already reads at runtime automatically.
#
# NEXT_PUBLIC_* variables are baked into the client JS bundle at BUILD
# TIME, not read at container runtime -- this Dockerfile declares a
# matching ARG so your host's build-time env var (however it's set)
# actually reaches `npm run build`.

FROM node:20-slim AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install

FROM node:20-slim AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

ARG NEXT_PUBLIC_API_BASE_URL
ENV NEXT_PUBLIC_API_BASE_URL=${NEXT_PUBLIC_API_BASE_URL}

RUN npm run build

FROM node:20-slim AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV HOSTNAME=0.0.0.0
ENV PORT=3000

COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

EXPOSE 3000
CMD ["node", "server.js"]

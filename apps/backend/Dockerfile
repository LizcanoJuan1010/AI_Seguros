# syntax=docker/dockerfile:1

# ---------- Stage 1: build ----------
FROM node:20-alpine AS builder
WORKDIR /app

# Install all deps (incl. dev) for building + prisma generate
COPY package.json package-lock.json ./
RUN npm ci

# Prisma needs the schema + config to generate the client
COPY prisma.config.ts tsconfig.json tsconfig.build.json nest-cli.json ./
COPY prisma ./prisma
COPY src ./src

# prisma.config.ts reads DATABASE_URL at load time; generate does not connect,
# so a dummy URL is enough here. The real URL is injected at runtime.
ENV DATABASE_URL="postgresql://build:build@localhost:5432/build?schema=public"
RUN npx prisma generate
RUN npm run build

# ---------- Stage 2: runtime ----------
FROM node:20-alpine AS runtime
WORKDIR /app
ENV NODE_ENV=production
ENV PORT=3000

# App metadata + prisma config/CLI are needed to run `prisma migrate deploy`
COPY package.json package-lock.json prisma.config.ts ./

# node_modules carries the prisma CLI + @prisma/client runtime (self-contained
# base64 WASM query compiler) + dotenv used by prisma.config.ts.
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/dist ./dist
COPY --from=builder /app/prisma ./prisma

COPY docker-entrypoint.sh ./docker-entrypoint.sh
RUN chmod +x ./docker-entrypoint.sh

EXPOSE 3000
ENTRYPOINT ["sh", "/app/docker-entrypoint.sh"]

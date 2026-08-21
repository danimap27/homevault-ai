# Dockerfile multi-stage del frontend HomeVault AI (Next.js standalone).
# Build:  docker build -t homevault-frontend ./frontend
# Run:    docker run -p 3000:3000 -e NEXT_PUBLIC_API_URL=http://<backend>:8000 homevault-frontend
# Nota: NEXT_PUBLIC_* se incrusta en build; para otra URL de API hay que
# reconstruir la imagen (o pasarla como build-arg si se parametriza).

FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci --no-audit --no-fund

FROM node:22-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# NEXT_PUBLIC_API_URL se hornea en el bundle del navegador en build time.
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
RUN addgroup -S nodejs && adduser -S nextjs -G nodejs
COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
USER nextjs
EXPOSE 3000
ENV PORT=3000 HOSTNAME=0.0.0.0
CMD ["node", "server.js"]

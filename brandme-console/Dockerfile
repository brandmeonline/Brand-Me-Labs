ARG NODE_VERSION=24.21.0
FROM node:${NODE_VERSION}-bookworm-slim AS build
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
RUN corepack enable && corepack prepare pnpm@10.34.6 --activate
COPY . .
RUN pnpm install --frozen-lockfile --filter @brandme/console... && mkdir -p brandme-console/public && pnpm --filter @brandme/console build

FROM node:${NODE_VERSION}-bookworm-slim AS runtime
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3002 HOSTNAME=0.0.0.0
COPY --from=build --chown=node:node /app/brandme-console/.next/standalone ./
COPY --from=build --chown=node:node /app/brandme-console/public ./brandme-console/public
COPY --from=build --chown=node:node /app/brandme-console/.next/static ./brandme-console/.next/static
USER node
EXPOSE 3002
CMD ["node", "brandme-console/server.js"]

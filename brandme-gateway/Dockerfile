# Build from the repository root so workspace dependencies retain their paths.
ARG NODE_VERSION=24.21.0
FROM node:${NODE_VERSION}-bookworm-slim AS build
WORKDIR /app
RUN corepack enable && corepack prepare pnpm@10.34.6 --activate
COPY . .
RUN pnpm install --frozen-lockfile --filter @brandme/gateway... && pnpm --filter @brandme/gateway build

FROM node:${NODE_VERSION}-bookworm-slim AS runtime
ENV NODE_ENV=production
WORKDIR /app/brandme-gateway
# Keep the frozen workspace dependency graph, including contracts. Legacy
# pnpm deploy resolves dependencies again instead of using a frozen lockfile.
COPY --from=build --chown=node:node /app/node_modules /app/node_modules
COPY --from=build --chown=node:node /app/packages/contracts /app/packages/contracts
COPY --from=build --chown=node:node /app/brandme-gateway/node_modules ./node_modules
COPY --from=build --chown=node:node /app/brandme-gateway/dist ./dist
COPY --from=build --chown=node:node /app/brandme-gateway/package.json ./package.json
USER node
EXPOSE 3001
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 CMD node -e "fetch('http://127.0.0.1:'+(process.env.PORT||3001)+'/healthz').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"
CMD ["node", "dist/index.js"]

# Copyright (c) Brand.Me, Inc. All rights reserved.
#
# Brand.Me chain service — Midnight rights adapter.
# Prover keys are regenerated from the pinned compactc and verified against
# contracts/artifact-manifest.json; the service refuses to start serving
# proving material that does not match.

FROM node:22-bookworm-slim AS build
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl unzip ca-certificates && rm -rf /var/lib/apt/lists/*
RUN corepack enable && corepack prepare pnpm@10.34.6 --activate
COPY . .
RUN pnpm install --frozen-lockfile --filter @brandme/chain...
WORKDIR /app/brandme-chain
RUN pnpm compact:compile && pnpm compact:verify && pnpm build

FROM node:22-bookworm-slim AS runtime
ENV NODE_ENV=production
WORKDIR /app/brandme-chain
COPY --from=build /app/node_modules /app/node_modules
COPY --from=build /app/brandme-chain/node_modules ./node_modules
COPY --from=build /app/brandme-chain/dist ./dist
COPY --from=build /app/brandme-chain/package.json ./package.json
RUN useradd -u 1000 -m brandme && chown -R brandme /app
USER brandme
EXPOSE 3001
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 CMD node -e "fetch('http://127.0.0.1:'+(process.env.PORT||3001)+'/health').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"
CMD ["node", "dist/src/index.js"]

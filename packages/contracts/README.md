# @brandme/contracts

Generated API vocabulary. **Inputs (read-only):** `docs/design/brandme/contracts/domain.schema.json` plus `src/foundation-schemas.json` (additive extensions; a name that shadows a spec `$def` fails generation) and `scripts/endpoints.mjs` (chapter 03 §6 inventory).

| Output | Use |
|---|---|
| `generated/openapi.json` | OpenAPI 3.1, `servers: /api/v1`; every operation carries `x-brandme-owner` (lane) and `x-brandme-status` (`implemented` / `reserved`) |
| `generated/api.ts`, `generated/schemas.ts` | TypeScript types (openapi-typescript) — `import type { PersonaPatch } from '@brandme/contracts'` |
| `src/client.ts` | Typed client (openapi-fetch); adds `X-CSRF-Token` on unsafe methods |
| `python/brandme_contracts/models.py` | Pydantic v2 models (datamodel-code-generator) for Python services |

Conventions: snake_case on the wire, no client-side renaming; revisions and money minor units are decimal strings; errors are `application/problem+json`. `Idempotency-Key` / `If-Match` are declared per operation.

Commands: `pnpm contracts:generate` (writes), `pnpm contracts:check` (CI drift gate: fails if any generated file differs from a fresh generation). Lanes add endpoints by editing `scripts/endpoints.mjs` and schemas in `src/foundation-schemas.json` (or a lane-specific file proposed at integration), then regenerating — never by hand-editing `generated/`.

**Python validation rule:** the generated pydantic models cannot express JSON Schema `if/then` conditionals. `DecisionResponse` (alternative requires a reference) and `ChainOperation` (finalized requires a transaction reference) pass the models alone. Python services must validate wire input with `jsonschema` against `generated/domain.schema.json` before building models (`tests/foundation/test_contract_models.py` pins this gap).

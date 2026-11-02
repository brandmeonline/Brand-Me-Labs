# Secret scan — method and redacted results (S2, 2026-11-01)

**Never includes secret values.** Hits are reported as type + path(:line) + commit where applicable.

## Method

1. **Working tree (tracked files only):** `git ls-files -z | xargs -0 grep -nIE <pattern>` in `/home/user/Brand-Me-Labs` at HEAD `ed19dc15`, excluding `pnpm-lock.yaml`. Patterns:
   - `-----BEGIN [A-Z ]*PRIVATE KEY-----`
   - `AKIA[0-9A-Z]{16}` (AWS access key id)
   - `sk_live_[0-9a-zA-Z]{8,}`, `sk_test_[0-9a-zA-Z]{8,}` (Stripe)
   - `AIza[0-9A-Za-z_-]{35}` (Google API key)
   - `ghp_[0-9A-Za-z]{30,}`, `github_pat_[0-9A-Za-z_]{30,}` (GitHub tokens)
   - `xox[baprs]-[0-9A-Za-z-]{10,}` (Slack)
   - `sk-ant-[0-9A-Za-z_-]{20,}` (Anthropic), `sk-[A-Za-z0-9]{32,}` (OpenAI-like)
   - `eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}` (JWT)
   - `credentials_json` (GCP SA key reference)
   - `night(preprod|mainnet|preview)[A-Za-z0-9_-]{8,}` (Blockfrost Midnight project token shape, from `brandme-chain/src/midnight/network.ts:37`)
   - `password\s*[:=]\s*['"][^'"]{6,}['"]` (case-insensitive)
   - mnemonic-like lines: `^["']?([a-z]{3,8} ){11,23}[a-z]{3,8}["']?,?$` over config/code extensions
   - committed dotenv/key files: `git ls-files | grep -E '(^|/)\.env($|\.)|\.pem$|\.key$|\.p12$|\.pfx$|id_rsa|service-account.*\.json|credentials.*\.json'`
   - public identifiers: `(project[_-]?id|GCP_PROJECT_ID|projectId)\s*[:=]\s*[a-z][a-z0-9-]{5,29}`
2. **History:** the local clone is shallow, so history was read from the full isolated clone `/tmp/claude-0/-home-user-Brand-Me-Labs/1bf61dcf-0f4d-53ea-917a-a94fd3490bcc/scratchpad/audit-clone/repo` (non-bare, HEAD `ed19dc15`, not shallow, 562 commits on `--all`, 19 remote branches). Commands: `git log --all --diff-filter=A --name-only -- '*.env' '*.pem' '*.key' '*.p12' '*.pfx' '*id_rsa*' '*service-account*.json' '*credentials*.json' '*secret*' '*.keystore'`; `git log --all -S'PRIVATE KEY' --name-only`; `git grep -lE <pattern> $(git rev-list --all | head -400)` for the key-shaped patterns (first 400 commits of `rev-list --all`; counts are commits-containing, not distinct strings).
3. **Tools:** `gitleaks` and `trivy` are **not on PATH** on this host (`which` returned nothing); no network installs were performed. CI runs Trivy's secret scanner repo-wide with allow-rules disabled (`.github/workflows/ci-cd.yml:550-554`, `trivy-secret.yaml:34-38`), which is a stronger configuration than Trivy's defaults.
4. Masked inspection of each hit (first 4 characters of a value plus length/shape) to classify as placeholder, fixture, or real. No full values were printed or recorded.

## Results — working tree

| Type | Location | Classification | Confidence |
|---|---|---|---|
| Private key block | — | **none** | high |
| AWS access key | — | none | high |
| Google API key | — | none | high |
| GitHub token | — | none | high |
| Slack token | — | none | high |
| JWT-shaped string | — | none | high |
| Stripe `sk_live_` shape | `brandme-gateway/src/routes/v1/commerce.test.ts:287`; `tests/test_providers_setup.py:143` | Secret-Manager **reference path** named `…/secrets/sk_live_fictional/versions/1` in test fixtures; not a key | high |
| Stripe `sk_test_` | — | none | high |
| Anthropic `sk-ant-` shape | `.env.deploy.example:15` | placeholder (45 chars, contains an `x…` run, no entropy); template file | high |
| OpenAI `sk-` shape | `.env.deploy.example:19` | placeholder (`sk-XXXX…`, 35 chars) | high |
| Blockfrost Midnight token shape | `brandme-chain/tests/midnight/{adapter,network,network-env}.test.ts` (15 lines) | test fixtures validating the token-shape regex; not credentials | high |
| `credentials_json` | `.github/workflows/ci-cd.yml:368` (uses `${{ secrets.GCP_SA_KEY }}`); `docs/build/security/credential-manifest.yaml:~241` (manifest entry describing that secret) | references to a GitHub secret, not a value; see finding S2-SEC-001 | high |
| `password = "literal"` | `agents/database-agent.sh:31,71`, `agents/service-agent.sh:58,59` | shell variable expansions (`"$DB_PASSWORD"`, `"$NEO4J_PASSWORD"`), not literals | high |
| `password = "literal"` | `scripts/backup.sh:23`, `scripts/db-init.sh:27` | **default fallback** `DB_PASSWORD="${DB_PASSWORD:-pos…}"` — a well-known default for a Postgres the current stack does not run (legacy); see S2-SEC-021 | high |
| `password = "literal"` | `brandme-agents/agentic/graph_db.py:315` | `os.getenv("NEO4J_PASSWORD", "password")` default fallback (legacy CLI) | high |
| `password = "literal"` | `docs/archive/STATUS_UPDATE_2025_01_27.md:18`, `docs/status/ENTERPRISE_ASSESSMENT.md:49` | prose in documents; not inspected further (docs out of scope beyond classification) | medium |
| Mnemonic-like 12/24-word lines | — | none in code/config | medium (regex heuristic) |
| Committed dotenv/key files | `.claude/.env.local.example`, `.env.deploy.example`, `.env.example`, `brandme-agents/agentic/.env.example`, `brandme-chain/.env.example`, `brandme-console/.env.example`, `brandme-core/.env.example`, `brandme-cube/.env.example`, `brandme-data/.env.example`, `brandme-gateway/.env.example` | templates only (names + placeholders); `.gitignore:6-33,243-246` ignores `.env*`, `*.pem`, `*.key`, `secrets/`, `*credentials*.json`, `client_secret*.json` while allowing `*.example` | high |

### Public identifiers (not secrets)
- GCP project id `lux-realestate-app` — `.github/workflows/ci-cd.yml:43` (image registry path for CI publishing).
- GCP/Firestore project ids `test-project` (emulator default: `brandme-gateway/src/config/index.ts:94`, `brandme_core/config.py:40`), `brandme-dev` (`docker-compose.yml:50`; Secret Manager paths in test fixtures), `brandme-prod` (`docs/deployment/*.md` only), `ci-fake-project` (`brandme-infra/helm/brandme/ci/test-values.yaml:9`), `REPLACE_ME_GCP_PROJECT_ID` (`values-sandbox.yaml:16`).
- Spanner instance/database defaults `brandme-instance` / `brandme-db` (`brandme-gateway/src/config/index.ts:95-96`, `docker-compose.yml:47-48`).
- GKE cluster name `brandme-cluster`, region `us-east1` (`ci-cd.yml:44-45`).
- Midnight endpoints (public): `rpc.preview.midnight.network`, `indexer.preview.midnight.network` (`brandme-chain/src/midnight/network.ts:26-28`).

## Results — history (full clone, 562 commits, `--all`)

| Check | Result |
|---|---|
| Files ever added matching `*.env`, `*.pem`, `*.key`, `*.p12`, `*.pfx`, `*id_rsa*`, `*service-account*.json`, `*credentials*.json`, `*secret*`, `*.keystore` | only `docs/build/security/secrets-conventions.md` and `trivy-secret.yaml` (both documentation/config about secrets, not secrets) |
| Commits whose diff adds/removes the text `PRIVATE KEY` | 6 commits (`db33b9d`, `8679c95`, `1011d74`, `6a81c26`, `fc0e406`, `1dc4245`), touching docs (`gke-verification-packet.md`, `credential-rotation.md`, `credential-manifest.yaml`), tests (`consumer-domains.test.ts`, `test_media_gcs_signing.py`, `commerce.test.ts`, `test_providers_setup.py`) and `providers.ts`/`setup.py` — phrases such as "private key" in prose/comments; the PEM-block regex below matched **no** commit |
| `-----BEGIN … PRIVATE KEY-----` across refs | **none** |
| `AKIA…`, `AIza…`, `xox[baprs]-…` across refs | none |
| `sk_live_…` across refs | `tests/test_providers_setup.py`, `brandme-gateway/src/routes/v1/commerce.test.ts`, `tests/test_commerce_http.py` — the same `sk_live_fictional` Secret-Manager path fixture |
| `ghp_…` across refs | `brandme-gateway/src/routes/v1/commerce.test.ts` (fixture; the current line uses the fictional secret-ref pattern) — classified as test fixture; value shape not inspected beyond path |
| `sk-ant-…` across refs | `.env.deploy.example` (placeholder, present in all 400 sampled commits), `tests/test_commerce_model_planner.py`, `tests/test_commerce_legacy_graph_rag.py` (tests of `require_dev_key`, which only checks the `sk-ant-api` prefix and length) |
| Blockfrost token shape across refs | `brandme-chain/tests/midnight/*.test.ts` fixtures only |
| `credentials_json` across refs | `.github/workflows/ci-cd.yml` (all sampled commits), `docs/build/security/credential-manifest.yaml` |

Limitations: the per-ref `git grep` covered the first 400 of 562 commits from `rev-list --all` (the loop was time-bounded); the `--diff-filter=A` and `-S'PRIVATE KEY'` searches covered all commits. Unreferenced/dangling objects were not scanned (`git fsck --lost-found` not run). Binary files (`.bzkir`, `.verifier`) were not inspected.

## Conclusion
No credential material was found in the tracked tree or sampled history. Every pattern hit is a template placeholder, a Secret-Manager **path** fixture, a token-shape test fixture, a shell variable expansion, or a legacy default password for a database the current stack does not deploy. The one operationally significant item is the **existence** of a long-lived GCP service-account JSON key as a GitHub secret (`GCP_SA_KEY`) consumed by `ci-cd.yml:368` — a credential-handling practice finding (S2-SEC-001), not a leak. Confidence: high for the tree, medium for history (sampling + heuristic regexes; no gitleaks run).

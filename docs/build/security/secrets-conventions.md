# Secrets conventions

Status (2026-10-23, base `744d593`): **design and inventory only.** No secret,
key, service account, Secret Manager entry or GitHub secret was created while
writing this. The live GitHub secret, variable and environment state could not be
read: those APIs return 403 from the build environment. The GCP state could not be
read either (no credentials). The repository is **public**, so anything committed
is published.

Related files:

- [credential-manifest.yaml](credential-manifest.yaml) lists every name. It is
  checked by [`scripts/check-credential-manifest.mjs`](../../../scripts/check-credential-manifest.mjs).
- [lane-service-accounts.md](lane-service-accounts.md) defines the per-lane identities.
  [`scripts/provision/gcp-dev-identities.sh`](../../../scripts/provision/gcp-dev-identities.sh)
  creates them.
- [credential-rotation.md](../runbooks/credential-rotation.md) is the rotation and
  exposure runbook.
- Spec requirements:
  - Secret Manager with service-specific access, name-only templates, and rotation
    that keeps cursors ([03 §Security](../../design/brandme/03-architecture-data-api.md)).
  - Write-only provider secrets ([05](../../design/brandme/05-commerce-agents-connectors.md)).
  - A documented credential rotation ([06](../../design/brandme/06-delivery-verification.md)).

## One vocabulary: the BRANDME_MODE words

Every secret, service account, bucket, topic and GitHub Environment is named
with the mode words `development`, `sandbox` and `production`. Never use
`dev`/`staging`/`prod`, with one exception: the 3-letter service-account code
below.

`demo` holds no secrets. Local `development` uses throwaway values and the
emulators. It never reads Secret Manager.

The code already enforces this vocabulary, so the convention follows it rather
than inventing a parallel one:

| Code-enforced rule | Where |
|---|---|
| `ENVIRONMENT` must equal `BRANDME_MODE` (otherwise the service refuses to start) | `brandme_core/read_api/config.py:26`, `brandme_core/privacy_exports/config.py:24`, `brandme_core/events/worker.py:38` |
| The export bucket must start with `brandme-<mode>-exports-` | `brandme_core/privacy_exports/config.py:39` |
| Pub/Sub outbox topics must start with `brandme-<ENVIRONMENT>-` | `brandme_core/events/pubsub.py:51-52`, `brandme_core/events/README.md:18` |
| Strict modes are `sandbox` and `production` | `brandme_core/config.py:99-108` (`Mode.is_strict`) |

Known splits that still use other words (not changed here):

- The gateway's legacy `environment` field maps sandbox to `staging`
  (`brandme-gateway/src/config/index.ts:167`).
- brandme-chain reads `ENVIRONMENT`, not `BRANDME_MODE`
  (`brandme-chain/src/config/index.ts:15,47`).
- Terraform and the old deploy scripts use dev/staging/prod.

The three tracked legacy files `.env.development`, `.env.staging` and
`.env.production` were deleted in this change. They held dev placeholder
passwords and names no code reads. One legacy script still reads them; see
"Open items" in the runbook.

## Layer 1: runtime environment variable names (the code contract)

- **Never rename an existing name.** Names are the contract between code, manifests,
  charts and open lane PRs. A name that breaks the convention keeps its name and gets
  a note in the manifest. Examples:
  - `MIDNIGHT_BLOCKFROST_PROJECT_ID` is a credential despite its `_PROJECT_ID` suffix.
  - `NORDSTROM_IMPACT_CREDENTIAL_SECRET` holds a Secret Manager reference, not a secret.
- **New names** are `<SCOPE>_<PURPOSE>_<TYPE>`, where TYPE is one of:

  | TYPE | Meaning |
  |---|---|
  | `_TOKEN` | bearer credential |
  | `_KEY` | private or signing key material |
  | `_KID` | key id; not secret |
  | `_SEEDS` | wallet seeds |
  | `_SECRET_REF` | a Secret Manager resource name; the reference is not secret |
  | `_URL` | endpoint; not secret |

  For example, the commerce lane's proposed `COMMERCE_DOMAIN_ASSERTION_KEY` and
  `COMMERCE_DOMAIN_ASSERTION_KID`.
- Put no mode, environment or `BM_` prefix inside a runtime name. The deployment
  supplies the mode.
- **No secret may use `NEXT_PUBLIC_`.** Next.js compiles those values into the
  browser bundle at build time. The checker fails on any `NEXT_PUBLIC_` name
  matching the secret pattern, in code, templates or the manifest.
- Templates (`*.env.example`) list names with empty values or `<placeholders>`, and
  comments. They never hold a value, not even a "dev" one.

## Layer 2: GCP Secret Manager ids

`brandme-<mode>-<lane>-<purpose-kebab>`

- `<mode>` is `sandbox` or `production`. Every mode has its own secret: one value
  is never shared between modes. This matters for the Midnight Blockfrost token:
  one variable carries either the Preprod or the Mainnet value
  (`brandme-chain/src/midnight/network.ts:36-52`).
- `<lane>` is the lane that owns the contract:

  | Code | Lane |
  |---|---|
  | `fnd` | foundation |
  | `com` | commerce-agents |
  | `dom` | consumer-domains |
  | `rts` | midnight-rights |
  | `ui` | consumer-ui |
  | `ar` | spatial-ar |

- `<purpose-kebab>` is the runtime name in lower case with `_` turned into `-`.
  For example, `RIGHTS_SERVICE_TOKEN` in sandbox becomes
  `brandme-sandbox-rts-rights-service-token`.
- Labels on every secret:
  - `lane`
  - `owner` (the lane name, for example `midnight-rights`)
  - `rotation-days` (days, or `event-driven`)
  - `consumers` (service-account keys joined with `_`, because label values allow
    only `[a-z0-9_-]`)
- Access is granted **per secret** (`roles/secretmanager.secretAccessor` on that
  secret only). The one prefix grant is for commerce provider credentials. Those
  live under `brandme-<mode>-com-provider-*`, which is narrower than `-com-`, so
  the commerce domain cannot read the gateway's planned assertion signing key
  `brandme-<mode>-com-domain-assertion-key`. Secret Manager IAM conditions must use
  the **project number** (`projects/<number>/secrets/...`), not the project id.

## Layer 3: GitHub

- Prefer secrets scoped to a **GitHub Environment** named exactly `sandbox` or
  `production`, with required reviewers and deployment-branch rules.
  - The secret name equals the runtime name, so a workflow maps
    `NAME: ${{ secrets.NAME }}` one to one.
  - Example: `MN_PREPROD_SEEDS` and `MIDNIGHT_BLOCKFROST_PROJECT_ID` in Environment
    `sandbox`, because Preprod is the sandbox network.
- Use a repository-level secret only when it is unavoidable, named
  `BM_<MODE>_<LANE>_<PURPOSE>` (for example `BM_SANDBOX_RTS_MN_PREPROD_SEEDS`).
- Non-secret identifiers are **repository variables**:
  - `BM_GCP_PROJECT_ID`
  - `BM_GCP_REGION`
  - `BM_GKE_CLUSTER`
  - `BM_GCP_WIF_PROVIDER`
  - `BM_GCP_DEPLOYER_SA`
  - `BM_DEPLOY_ENABLED` (the switch that gates the deploy job)

  Workflows read them as `${{ vars.NAME }}`. A secret is never stored as a variable.
- **Retire `GCP_SA_KEY`** (`.github/workflows/ci-cd.yml:358`, image publishing; the deploy job already uses WIF), a long-lived JSON
  key, in favour of Workload Identity Federation:
  - Add `permissions: id-token: write` to the jobs that authenticate. A job-level
    `permissions:` block replaces the workflow-level one, so also restate
    `contents: read`.
  - Pass `workload_identity_provider: ${{ vars.BM_GCP_WIF_PROVIDER }}` and
    `service_account: ${{ vars.BM_GCP_DEPLOYER_SA }}` to
    `google-github-actions/auth`.
  - Delete the key and the secret after the first green run.
- The WIF provider must pin both the repository and the ref. This repository is
  public, so an unpinned provider would accept tokens from any workflow run.
  [lane-service-accounts.md](lane-service-accounts.md#github-workload-identity-federation)
  has the exact condition.

## Layer 4: Google service accounts

`bm-<env3>-<lane>-<purpose>`

- `env3` is `dev`, `sbx` or `prd`. Service-account ids are 6 to 30 characters, and
  this 3-letter code is the only place the short form is allowed.
- Examples: `bm-sbx-rts-chain`, `bm-sbx-rts-export-wkr`.
- Each workload binds to one Kubernetes ServiceAccount through GKE Workload
  Identity. The KSA is named `<release>-<component>` in namespace `brandme` (for
  example `brandme-read-api`), matching the chart's ServiceAccount template.
- **No service account ever has a key.**
- Use one GCP project per mode where possible. `brandme_core/events/README.md:13-14`
  already asks for separate databases and workload identities per environment.

## The credential manifest

[credential-manifest.yaml](credential-manifest.yaml) has one row per secret,
credential or secret-shaped name that code, CI, templates or deploy scripts
reference. Field meanings are in the file header.

The `status` values:

| Status | Meaning |
|---|---|
| `active` | Read by wired code or CI today. Provision it for the listed modes. |
| `planned` | Designed (spec, lane branch or unmounted code), but no deployable process reads it yet. |
| `legacy-unread` | No wired, deployable process reads it. The remaining references are legacy or not-wired code, deploy scripts or templates. **Never provision**; remove the reference when the legacy code goes. |
| `refused` | Code reads it only so that strict modes can refuse it (`JWT_SECRET`). Never provision. |

`created_by_this_lane` is `false` everywhere: no credential was created when the
manifest was written. Legacy code is not excluded from the scan. Its names are
listed as `legacy-unread`, so the inventory stays complete and a revived legacy
path shows up in review.

### Manifest format (the YAML subset)

The checker parses the manifest itself, with Node built-ins only, and refuses
anything outside this subset, reporting the line number. It never guesses.

- Two-space indentation and no tabs. No anchors, aliases, tags, block scalars
  (`|`, `>`), flow mappings (`{}`) or document markers.
- Scalars are plain, `'single-quoted'` (`''` escapes a quote) or `"double-quoted"`
  (only `\"`, `\\` and `\n` escapes). Plain `true`, `false`, `null` and integers
  are typed.
- Quote these values:
  - any value containing `: ` or ` #`
  - every regex
  - anything another YAML parser would type differently: `yes`/`no`/`on`/`off`,
    floats, dates, leading zeros
- Lists are block lists (`- item`) or one-line flow lists (`[a, b]`). Quote flow
  items that contain `:`.

On this tree, the parsed result is identical to PyYAML 6.0.3's `safe_load`. The
check was `node scripts/check-credential-manifest.mjs --dump-manifest` against
`yaml.safe_load`, comparing the two results.

### Adding a credential

1. Pick the name with Layer 1. Add the row with `status: planned`, the Secret Manager
   id pattern, the GitHub location, the validation regex, `distinct_from` (it must be
   symmetric) and the rotation class.
2. When code starts reading it, add the `path:line` consumers and switch the row to
   `active`.
3. Run `node scripts/check-credential-manifest.mjs`.
4. Provision it with the owning lane's identity (per-secret accessor only). Never put
   the value in a template, a test fixture or a document.

## The checker

`node scripts/check-credential-manifest.mjs [--strict] [--json] [--root DIR] [--manifest PATH]`

It scans **git-tracked** files:

- `*.ts`, `*.tsx`, `*.js`, `*.mjs`, `*.cjs`, `*.py`, `*.sh`
- `docker-compose*.yml`
- `.github/workflows/*.yml`

It looks for these environment reads:

| Language | Reads matched |
|---|---|
| JS/TS | `process.env.X`, `process.env['X']`, `import.meta.env.X`, `env.X` and `env['X']` on an env object, `vi.stubEnv('X')` |
| Python | `os.environ[...]`, `os.environ.get/pop/setdefault(...)`, `os.getenv(...)`, `getenv(...)`, `env.get(...)` and `env[...]` on a mapping, `monkeypatch.setenv/delenv` |
| Shell | `$X`, `${X...}` |
| Workflows | `${{ secrets.X }}`, `secrets['X']`, `${{ env.X }}`, plus shell reads |

A name is secret-shaped when it matches
`/(KEY|SECRET|TOKEN|PASSWORD|CREDENTIAL|PRIVATE|SEED|SEEDS|MNEMONIC|DSN)/`.

**Fails (exit 1) on:**

- a secret-shaped read with no manifest row (reported once per name, with
  locations);
- a secret-shaped `NEXT_PUBLIC_` name;
- a tracked env file that is not `*.example` (`.env*`, `*.env` and `.envrc`);
- a secret-shaped name declared in an env template without a manifest row;
- a malformed manifest: missing or unknown fields, bad enums, a Secret Manager
  lane that differs from `lane_owner`, a non-symmetric `distinct_from`, an
  unanchored or invalid regex, a GitHub Environment secret whose name differs
  from the runtime name, or a planned secret whose name lacks a TYPE suffix.

**Warns (exit 0; `--strict` turns warnings into failures) on:**

- a manifest consumer whose file is gone or no longer contains the name (stale);
- a consumer line that drifted;
- an `active` row with no live consumer;
- a value in a template for a secret name;
- a credential embedded in a template URL;
- an untracked manifest (commit it; `.gitignore` re-includes `docs/build/`).

**Excluded:** generated and vendored paths only:

- `node_modules/`, `vendor/`, `vendored/`, `third_party/`
- `dist/`, `build/`, `out/`, `coverage/`, `.next/`
- `generated/` (the `pnpm contracts:generate` output)
- `brandme-chain/contracts/managed/` (Compact compiler output)
- `*.min.js`, `*.d.ts`

**Known limits** (the reason the manifest also lists names by hand):

- Indirect reads are not detected, for example a tuple of names fed to
  `env.get(k)` (`brandme_core/read_api/config.py:34`) or a dynamic `env[flag]`.
- Credentials whose names are not secret-shaped (`MIDNIGHT_BLOCKFROST_PROJECT_ID`)
  are invisible to the scan.
- These are not scanned:
  - JSON (`.mcp.json`)
  - Helm values, Terraform and Dockerfiles
  - lower-case env-object reads
  - SDKs that read a key implicitly (for example LangChain reading
    `ANTHROPIC_API_KEY`)
  - compose files outside the root `docker-compose*.yml` (for example
    `brandme-chain/tests/network/compose.yml`)
- Two read forms escape detection: JS destructuring
  (`const { X_TOKEN } = process.env`) and an aliased Python import
  (`from os import environ as E; E['X']`). Neither occurs in the tree today.

Tests: `node --test scripts/check-credential-manifest.test.mjs` runs the checker
against synthetic git repositories.

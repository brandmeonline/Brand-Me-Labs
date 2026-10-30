# Credential rotation and exposure runbook

Status (2026-10-25, base `bf31c98`, after PR #51 commerce and PR #56 consumer UI merged; revised
2026-10-30 on `375180b`, with the consumer-domains chart wiring merged):
**nothing in this runbook has been run.** No sandbox or production deployment exists,
and no credential has been provisioned from this repository. Every block below is
`not run` until someone runs it and records evidence (section 7). The repository is **public**.

Spec requirements:

- rotation without losing ingestion cursors or in-flight reconciliation
  ([03](../../design/brandme/03-architecture-data-api.md), Security);
- a documented credential rotation ([06](../../design/brandme/06-delivery-verification.md)).

## 1. Scope: the active set on this head

The source of truth is [credential-manifest.yaml](../security/credential-manifest.yaml),
re-audited on `bf31c98`. These rows are `secret: true` and `status: active`. Each one has a
block in section 5.

| Block | Name(s) | Class | Where the value lives | Consumers on this head |
|---|---|---|---|---|
| 5.1 | `RIGHTS_SERVICE_TOKEN`, `PRIVACY_SERVICE_TOKEN`, `PRIVACY_EXPORT_SERVICE_TOKEN`, `CHAIN_SERVICE_TOKEN` | internal-bearer | Secret Manager `brandme-<mode>-rts-<name-kebab>` → SecretSync → Kubernetes Secret (key `value`) → env | rendered chart, table in 5.1 |
| 5.2 | `CONSUMER_DOMAIN_ASSERTION_KEY` (+ `_KID`, not secret) | signing-key | Secret Manager `brandme-<mode>-dom-domain-assertion-key` → SecretSync → Kubernetes Secret (key `value`) → gateway env; the kid and the public JWKS are chart values | gateway signs (`brandme-gateway/src/config/index.ts:173-174`, `src/services/domains.ts:24-46`); the consumer-domain service verifies against public `CONSUMER_DOMAIN_ASSERTION_JWKS` (`brandme_core/domains/persona/app.py:93-94,116`) |
| 5.3 | `MIDNIGHT_BLOCKFROST_PROJECT_ID` | provider-token | Secret Manager `brandme-<mode>-rts-midnight-blockfrost-project-id`; GitHub Environment `sandbox` (designated) | `brandme-chain/src/config/index.ts:52`, Preprod runner `brandme-chain/scripts/test-midnight-preprod.mjs:6` |
| 5.4 | `MN_PREPROD_SEEDS` | test-wallet-seeds | GitHub Environment `sandbox` (designated); never Secret Manager | Preprod runner only (`test-midnight-preprod.mjs:7-9`) |
| 5.5 | `GCP_SA_KEY` | gcp-sa-key-legacy | GitHub repository secret | `.github/workflows/ci-cd.yml:368` (build-images only) |
| 5.6 | `STRIPE_TEST_WEBHOOK_SECRET`, `STRIPE_TEST_WEBHOOK_SECRET_PREVIOUS` | provider-token | developer's untracked env or the cloud dev environment's secrets (demo/development only) | `brandme_core/domains/providers/payments/stripe_test.py:54,160-161` |
| 5.7 | `STRIPE_TEST_SECRET_KEY` | provider-token | same as 5.6 | `stripe_test.py:54,162`; gated live suite `tests/test_commerce_stripe_live.py:27` |
| 5.8 | `BRANDME_DEV_ANTHROPIC_API_KEY` | provider-token | same as 5.6 | `brandme_core/orchestrator/model_planner.py:53,277`; gated live suite `tests/test_commerce_model_live.py:18` |
| 5.9 | `MAGIC_API_KEY` | provider-token | each developer's gitignored `.claude/.env.local` | `.mcp.json:9` (developer tooling only) |

Not in scope, and why:

- `COMMERCE_DOMAIN_ASSERTION_KEY`/`_KID` are `planned`. No file outside `docs/` names them on
  this head; commerce has no assertion signer yet. When one lands, the key follows block 5.2.
- `BRANDME_LOG_PSEUDONYM_KEY` and `BRANDME_LOG_REF_KEY` are `planned` and not provisioned.
  Rotating either one breaks log correlation with older lines; that is intended.
- `BRANDME_DEV_ASSERTION_KEY` (`local`) is generated fresh on every run of the consumer-ui dev
  harness (`brandme-frontend/lib/testing/start-dev-gateway.mjs:8`). There is nothing to rotate.
- Rows with status `legacy-unread` or `refused` are never provisioned. If one is found set
  anywhere, treat it as an exposure (section 6) and delete it.

Naming and identities: [secrets-conventions.md](../security/secrets-conventions.md) and
[lane-service-accounts.md](../security/lane-service-accounts.md). How the secrets first reach
the cluster: [gke-verification-packet.md](../deploy/gke-verification-packet.md) C-14/C-15.

## 2. Roles

| Role | Who | Does |
|---|---|---|
| Owner lane | the row's `lane_owner` in the manifest. `rts` (midnight-rights) owns the four service tokens and the Midnight credentials; `dom` (consumer-domains) owns the domain assertion key; `com` (commerce-agents) owns the Stripe and model keys; `fnd` (foundation) owns CI, GCP identity and developer tooling | keeps the row current; approves format changes |
| Rotator | an operator with, on the secret being rotated, `roles/secretmanager.secretVersionManager` (add, disable, enable and destroy versions: the generate, rollback and retire steps) and `roles/secretmanager.secretAccessor` (the digest checks, `sm_fp` and `wait_synced`); for 5.1, `roles/secretmanager.secretAccessor` on all four `brandme-<mode>-rts-*-service-token` secrets (the distinctness check reads the other three); and the `admin` ClusterRole bound in namespace `brandme` (patch the SecretProviderClass, `rollout restart`, `exec`, `port-forward`). Whether the secret sync add-on aggregates its `secretproviderclasses` resource into `admin` is not verified; `rotation-env.sh` checks it and, if not, the rotator also needs a Role with `get` and `patch` on it. 5.3 and 5.4 also need admin on the repository's `sandbox` Environment secrets; 5.5 is the break-glass role's | generates and adds the new version, pins it, rolls the workloads, records evidence |
| Approver | a second person (the GitHub Environment reviewer for `sandbox` and `production`) | approves the window and the evidence |
| Break-glass | the founder, or a named delegate with project owner rights | revokes or disables during an exposure, outside the normal window |

No workload identity can add secret versions; only people in the rotator role can.

## 3. Classes

| Class | Cadence | Rule |
|---|---|---|
| internal-bearer | about 90 days, and on any exposure | New random value. All four stay pairwise distinct. Server and gateway restart together. |
| signing-key | about 180 days | **Overlap by kid.** Publish the new public key before signing with it. Remove the old one only after the longest assertion lifetime. |
| provider-token | on exposure, or per provider policy | Regenerate at the provider, verify, then revoke the old one there. Never reuse a value across modes. |
| test-wallet-seeds | per test campaign, and on exposure | **Replace and sweep, never edit.** |
| gcp-keyless | nothing to rotate | No keys exist. Alert on key creation (open item, section 8). |
| gcp-sa-key-legacy | retire, do not rotate | `GCP_SA_KEY` only: block 5.5. |

## 4. Rules that apply to every block

1. **Never print a value.** Generators pipe straight into `gcloud secrets versions add
   --data-file=-`. Checks compare SHA-256 digests inside the shell or the pod, and print only
   "matches" or "differs", never the digest. Never use `set -x`, `-o yaml`/`-o json` on a
   Secret, or `gcloud secrets versions access` to a terminal.
2. **Pin explicit versions.** The SecretProviderClass from packet C-15 names `versions/N` for
   every secret, never `versions/latest`. Adding a version therefore changes nothing until
   its pin changes. Every token reaches pods as an env var through `secretKeyRef`, which is
   read only at pod start. So a rotation needs the pin change, the Kubernetes Secret
   refresh, and a `rollout restart` of exactly the consumers, all in one sitting. The secret
   sync add-on's refresh interval was not verified here (docs.cloud.google.com/secret-manager/docs/sync-k8-secrets);
   `wait_synced` below waits for the new value instead of assuming an interval.
3. **Fixed fields per block:** generate, store, pin, restart consumers, verify, rollback,
   evidence. Every command block starts with `set -euo pipefail`. Run each block as its own
   script, or in a fresh `bash --norc` sub-shell, so that a failure ends that block and not
   your login shell. Blocks pass state through `rotation-state.env` in the working directory;
   that file holds ids and version numbers only.
4. **Retire the old version** only after verification: disable it, and destroy it 7 days
   later if nothing broke.

### 4.1 Shell helpers (save as `rotation-env.sh` outside the repository; it holds no secret)

```bash
set -euo pipefail
export PROJECT_ID=REPLACE_ME          # the sandbox project (packet D1)
export MODE=sandbox NS=brandme SPC=brandme-sandbox-rts
[[ "$PROJECT_ID" != REPLACE_ME* && "$PROJECT_ID" =~ ^[a-z][a-z0-9-]{4,28}[a-z0-9]$ ]] || { echo "set PROJECT_ID" >&2; return 1 2>/dev/null || exit 1; }
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')
[[ "$PROJECT_NUMBER" =~ ^[0-9]+$ ]] || { echo "PROJECT_NUMBER lookup failed" >&2; return 1 2>/dev/null || exit 1; }
export PROJECT_NUMBER
kubectl config current-context        # must be the sandbox cluster (packet C-7)
[ "$(kubectl auth can-i patch secretproviderclasses.secrets-store.csi.x-k8s.io -n "$NS" 2>/dev/null || true)" = yes ] \
  || { echo "you cannot patch SecretProviderClasses in $NS: bind a Role with get and patch on them (section 2)" >&2; return 1 2>/dev/null || exit 1; }

# Digests are computed and compared here; none is ever printed.
sm_fp()  { gcloud secrets versions access "$2" --secret "$1" --project "$PROJECT_ID" | sha256sum | cut -d' ' -f1; }
k8s_fp() { kubectl -n "$NS" get secret "$1" -o jsonpath='{.data.value}' | base64 -d | sha256sum | cut -d' ' -f1; }
pod_fp() {  # pod_fp <deployment> <ENV_NAME>: digest of that env var inside the running pod
  case "$1" in
    brandme-gateway|brandme-chain) kubectl -n "$NS" exec "deploy/$1" -- node -e \
      "process.stdout.write(require('crypto').createHash('sha256').update(process.env['$2'] ?? '').digest('hex'))" ;;
    *) kubectl -n "$NS" exec "deploy/$1" -- python -c \
      "import hashlib,os,sys; sys.stdout.write(hashlib.sha256(os.environ.get('$2','').encode()).hexdigest())" ;;
  esac
}
same() { [ "$1" = "$2" ] && echo "matches: $3" || { echo "DIFFERS: $3" >&2; return 1; }; }
pinned() {  # pinned <secret-id>: the version the SecretProviderClass names
  kubectl -n "$NS" get secretproviderclass "$SPC" -o jsonpath='{.spec.parameters.secrets}' \
    | sed -nE "s#.*/secrets/$1/versions/([0-9]+)\".*#\1#p"
}
pin() {  # pin <secret-id> <version>: rewrite that one resourceName (resource names only, no values)
  local cur new
  cur=$(kubectl -n "$NS" get secretproviderclass "$SPC" -o jsonpath='{.spec.parameters.secrets}')
  new=$(printf '%s' "$cur" | sed -E "s#(/secrets/$1/versions/)[0-9]+\"#\1$2\"#")
  [ "$new" != "$cur" ] || { echo "pin for $1 unchanged (already $2, or not found)" >&2; return 1; }
  kubectl -n "$NS" patch secretproviderclass "$SPC" --type merge \
    -p "$(jq -n --arg s "$new" '{spec:{parameters:{secrets:$s}}}')"
}
wait_synced() {  # wait_synced <secret-id> <version>: the synced Kubernetes Secret (same name) holds it
  local want; want=$(sm_fp "$1" "$2")
  for _ in $(seq 1 60); do
    [ "$(k8s_fp "$1")" = "$want" ] && { echo "$1: Kubernetes Secret holds version $2"; return 0; }
    sleep 10
  done
  echo "$1: not synced to version $2 after 10 minutes; nothing restarted yet, pin back and stop" >&2; return 1
}
```

Each block below starts with `set -euo pipefail` and `. ./rotation-env.sh`.

## 5. Procedures

### 5.1 Internal bearer tokens (four)

These are the consumers in the rendered chart (`helm template` of
`brandme-infra/helm/brandme` with `ci/test-values.yaml`, run 2026-10-25). Each token
reaches the pod as an env var from the Kubernetes Secret of the same name:

| `NAME` | `ID` (sandbox) | Deployments that read it (restart all of them together) |
|---|---|---|
| `RIGHTS_SERVICE_TOKEN` | `brandme-sandbox-rts-rights-service-token` | `brandme-read-api`, `brandme-gateway` |
| `PRIVACY_SERVICE_TOKEN` | `brandme-sandbox-rts-privacy-service-token` | `brandme-read-api`, `brandme-gateway` |
| `PRIVACY_EXPORT_SERVICE_TOKEN` | `brandme-sandbox-rts-privacy-export-service-token` | `brandme-exports-api`, `brandme-exports-worker`, `brandme-gateway` |
| `CHAIN_SERVICE_TOKEN` | `brandme-sandbox-rts-chain-service-token` | `brandme-chain`, `brandme-gateway` |

Each server compares against exactly one token: `brandme_core/read_api/app.py:76`,
`brandme_core/privacy_exports/app.py:31`, `brandme-chain/src/routes/operations.ts:35`. While the
server and the gateway disagree, gateway calls get 401/403. The gateway reports that as 503
"The service could not authorize this request" (`brandme-gateway/src/services/rights.ts:31`).
Restarting both sides in one `rollout restart` keeps that window to the rollout itself. Chain
reconciliation resumes from its Spanner operation store, so no in-flight operation or
ingestion cursor is lost (section 5.10).

**Generate and store** (the new version is inert until pinned):

```bash
set -euo pipefail
. ./rotation-env.sh
NAME=RIGHTS_SERVICE_TOKEN ID=brandme-$MODE-rts-rights-service-token   # one row of the table
DEPLOYS="brandme-read-api brandme-gateway"                           # that row's deployments
OLD=$(pinned "$ID"); [[ "$OLD" =~ ^[0-9]+$ ]] || { echo "no pinned version for $ID" >&2; exit 1; }
# One generator for every token (packet C-14 uses the same): 64 chars of [A-Za-z0-9_-], which every
# consumer accepts (gateway src/config/index.ts:90-93, read_api/config.py:35, privacy_exports/config.py:42,
# brandme-chain/src/config/index.ts:20).
NEW=$(python3 -c 'import secrets; print(secrets.token_urlsafe(48), end="")' \
  | gcloud secrets versions add "$ID" --project "$PROJECT_ID" --data-file=- --format='value(name)')
NEW=${NEW##*/}
gcloud secrets versions access "$NEW" --secret "$ID" --project "$PROJECT_ID" | grep -Ex '[A-Za-z0-9._~+/-]{32,256}' >/dev/null \
  || { echo "version $NEW of $ID does not read back as a token; disable it and generate again" >&2; exit 1; }
# Pairwise distinct: this new version against the other three tokens' pinned versions.
dups=$(for t in rights-service-token privacy-service-token privacy-export-service-token chain-service-token; do
  s=brandme-$MODE-rts-$t; if [ "$s" = "$ID" ]; then sm_fp "$s" "$NEW"; else sm_fp "$s" "$(pinned "$s")"; fi
done | sort | uniq -d | wc -l)
[ "$dups" -eq 0 ] || { echo "a token value repeats; disable version $NEW and generate again" >&2; exit 1; }
printf 'NAME=%s ID=%s OLD=%s NEW=%s DEPLOYS="%s"\n' "$NAME" "$ID" "$OLD" "$NEW" "$DEPLOYS" > rotation-state.env
echo "$ID: pinned $OLD, added $NEW (not pinned yet)"
```

**Pin and restart consumers** (one sitting, in a quiet window):

```bash
set -euo pipefail
. ./rotation-env.sh; . ./rotation-state.env
pin "$ID" "$NEW"
wait_synced "$ID" "$NEW"
read -ra deps <<<"$DEPLOYS"; kubectl -n "$NS" rollout restart "${deps[@]/#/deploy/}"
for d in $DEPLOYS; do kubectl -n "$NS" rollout status "deploy/$d" --timeout=5m; done
```

**Verify:**

```bash
set -euo pipefail
. ./rotation-env.sh; . ./rotation-state.env
want=$(sm_fp "$ID" "$NEW")
for d in $DEPLOYS; do same "$(pod_fp "$d" "$NAME")" "$want" "$d $NAME = version $NEW"; done
case "$NAME" in
  RIGHTS_SERVICE_TOKEN|PRIVACY_SERVICE_TOKEN)
    kubectl -n "$NS" exec deploy/brandme-read-api -- python -m brandme_core.read_api --check ;;
  PRIVACY_EXPORT_SERVICE_TOKEN)
    kubectl -n "$NS" exec deploy/brandme-exports-api -- python -m brandme_core.privacy_exports --check
    kubectl -n "$NS" exec deploy/brandme-exports-worker -- python -m brandme_core.privacy_exports --check ;;
esac
# Through the gateway, on a port-forward (nothing is exposed publicly).
kubectl -n "$NS" port-forward deploy/brandme-gateway 18081:3001 >/dev/null 2>&1 & pf=$!
trap 'kill "$pf" 2>/dev/null' EXIT; sleep 3
curl -fsS -o /dev/null -w 'gateway /healthz %{http_code}\n' http://127.0.0.1:18081/healthz
if [ "$NAME" = RIGHTS_SERVICE_TOKEN ]; then
  # A public passport read needs the rights credential: 404 (unknown asset) is a pass, 503 is "could not authorize".
  code=$(curl -sS -o /dev/null -w '%{http_code}' "http://127.0.0.1:18081/api/v1/assets/$(python3 -c 'import uuid; print(uuid.uuid4())')/passport")
  [ "$code" != 503 ] && echo "rights path through the gateway: $code" || { echo "rights path: 503 could not authorize" >&2; exit 1; }
fi
if [ "$NAME" = CHAIN_SERVICE_TOKEN ]; then
  kubectl -n "$NS" port-forward deploy/brandme-chain 18082:3001 >/dev/null 2>&1 & pf2=$!
  trap 'kill "$pf" "$pf2" 2>/dev/null' EXIT; sleep 3
  curl -fsS -o /dev/null -w 'chain /health %{http_code}\n' http://127.0.0.1:18082/health
fi
```

`--check` prints one JSON status line and exits 0, or prints `{"status":"startup_refused"}` and
exits 2. The digest comparison is what proves the two sides agree. `PRIVACY_SERVICE_TOKEN` and
the chain operations routes need a member session, so no request probe without a session is
possible for them. Do not use `/api/v1/system/health` here: it also checks the legacy brain
service, which the chart does not deploy, so it reports `degraded` in the cluster
(`brandme-gateway/src/routes/v1/index.ts:67-81`).

**Rollback** (the old version is still enabled until the retire step):

```bash
set -euo pipefail
. ./rotation-env.sh; . ./rotation-state.env
pin "$ID" "$OLD"
wait_synced "$ID" "$OLD"
read -ra deps <<<"$DEPLOYS"; kubectl -n "$NS" rollout restart "${deps[@]/#/deploy/}"
for d in $DEPLOYS; do kubectl -n "$NS" rollout status "deploy/$d" --timeout=5m; done
gcloud secrets versions disable "$NEW" --secret "$ID" --project "$PROJECT_ID"
```

Then run the verify block with `NEW=$OLD`.

**Retire the old version** (after verification):

```bash
set -euo pipefail
. ./rotation-env.sh; . ./rotation-state.env
gcloud secrets versions disable "$OLD" --secret "$ID" --project "$PROJECT_ID"
# 7 days later, if nothing broke:
# gcloud secrets versions destroy "$OLD" --secret "$ID" --project "$PROJECT_ID"
```

**Evidence:** one row in section 7. Record versions OLD→NEW, the `--check` status lines, the
"matches" lines and the probe codes. Record no digests.

*Proposed, cross-lane, not implemented:* servers would also accept an optional `<NAME>_NEXT`,
validated with the same regex and distinctness rules and compared in constant time. The order
would then be: set `_NEXT` on the server and roll it; switch the gateway and roll it; promote
the new value, clear `_NEXT` and roll the server. That removes the 401 window, and it touches
midnight-rights code (read API, exports, chain) and foundation code (gateway config).

### 5.2 `CONSUMER_DOMAIN_ASSERTION_KEY` / `_KID` (ES256, kid overlap over two deploys)

- The gateway signs a fresh assertion per request: 30 s lifetime (`brandme-gateway/src/services/domains.ts:24`),
  `kid` from `CONSUMER_DOMAIN_ASSERTION_KID`.
- The domain service accepts at most a 60 s lifetime (`MAX_TTL`,
  `brandme_core/domains/persona/assertion.py:29`) with 30 s of clock skew (`:30`). It selects the
  public key by `kid` from `CONSUMER_DOMAIN_ASSERTION_JWKS`. That value is public P-256 JWKs only;
  a key with `d` is refused (`assertion.py:50-57`).
- Deployments: `brandme-gateway` (signer) and `brandme-consumer-domains` (verifier, one replica;
  KSA `brandme-consumer-domains-api`, GSA `bm-sbx-dom-api`).
- Where each part lives (`brandme-infra/helm/brandme`):

  | Part | Source | Reaches |
  |---|---|---|
  | private key (PKCS#8 PEM) | Secret Manager `brandme-sandbox-dom-domain-assertion-key`, synced to the Secret of the same name (packet C-15; `values-sandbox.yaml:35`) | gateway env `CONSUMER_DOMAIN_ASSERTION_KEY` (`templates/gateway.yaml:106`) |
  | kid | `consumerDomains.assertion.signingKid` (`values-sandbox.yaml:77`) | gateway env `CONSUMER_DOMAIN_ASSERTION_KID` (`templates/gateway.yaml:104-105`) |
  | public keys | `consumerDomains.assertion.jwks.keys` (`values-sandbox.yaml:78-80`) | domain service env `CONSUMER_DOMAIN_ASSERTION_JWKS` (`templates/core-workloads.yaml:71-72`) |

  The chart refuses a `signingKid` that names no key in the JWKS (`templates/validate.yaml:76`)
  and any JWK with `d` (`templates/_helpers.tpl:160`).
- The kid and the public keys are chart values, so each change ships as a **deploy**: a values
  PR merged to `main`, then a `v*` tag (packet C-20). Never `kubectl set env`; the next deploy
  would revert it.

Why two deploys: one deploy rolls the gateway and the domain service at the same time, so
gateway pods that sign with the new kid can be serving before the domain service pod that
knows it. **Deploy 1** publishes the new public key next to the old one. **Deploy 2** switches
the signer. A third, later deploy removes the old public key.

**Generate and store** (operator machine). Node writes the public JWK to a file and the PKCS#8
private key to stdout, which pipes straight into Secret Manager: the private key never touches
disk, a shell variable or a command argument. The new version is inert until it is pinned.

```bash
set -euo pipefail
. ./rotation-env.sh
ID=brandme-$MODE-dom-domain-assertion-key
OLD=$(pinned "$ID"); [[ "$OLD" =~ ^[0-9]+$ ]] || { echo "no pinned version for $ID" >&2; exit 1; }
OLD_KID=$(kubectl -n "$NS" exec deploy/brandme-gateway -- node -e 'process.stdout.write(process.env.CONSUMER_DOMAIN_ASSERTION_KID ?? "")')
[[ "$OLD_KID" =~ ^[A-Za-z0-9._-]{1,64}$ ]] || { echo "could not read the gateway's current kid" >&2; exit 1; }
KID="dom-$MODE-$(date -u +%Y%m%d%H%M)"
[ "$KID" != "$OLD_KID" ] || { echo "new kid equals the current one; wait a minute" >&2; exit 1; }
NEW=$(node -e 'const c=require("crypto"),f=require("fs");
  const {privateKey,publicKey}=c.generateKeyPairSync("ec",{namedCurve:"P-256"});
  const {kty,crv,x,y}=publicKey.export({format:"jwk"});
  f.writeFileSync(process.argv[1],JSON.stringify({kty,crv,kid:process.argv[2],x,y,use:"sig",alg:"ES256"})+"\n");
  process.stdout.write(privateKey.export({type:"pkcs8",format:"pem"}))' "public-jwk-$KID.json" "$KID" \
  | gcloud secrets versions add "$ID" --project "$PROJECT_ID" --data-file=- --format='value(name)')
NEW=${NEW##*/}
# The stored version is PKCS#8 P-256 and signs for the public JWK (checked in memory; prints one line).
gcloud secrets versions access "$NEW" --secret "$ID" --project "$PROJECT_ID" \
  | node -e 'const c=require("crypto"),f=require("fs");const pem=f.readFileSync(0,"utf8"),pub=JSON.parse(f.readFileSync(process.argv[1],"utf8"));
    const k=c.createPrivateKey(pem),m=c.randomBytes(32);
    if(!pem.startsWith("-----BEGIN PRIVATE KEY-----")||k.asymmetricKeyDetails.namedCurve!=="prime256v1"||"d" in pub
      ||!c.verify("sha256",m,c.createPublicKey({key:pub,format:"jwk"}),c.sign("sha256",m,k)))process.exit(1);
    process.stdout.write("version pairs with kid "+pub.kid+"\n")' "public-jwk-$KID.json" \
  || { echo "version $NEW does not pair with public-jwk-$KID.json; disable it and generate again" >&2; exit 1; }
printf 'ID=%s OLD=%s NEW=%s OLD_KID=%s NEW_KID=%s\n' "$ID" "$OLD" "$NEW" "$OLD_KID" "$KID" > rotation-state.env
# The line to append under consumerDomains.assertion.jwks.keys in deploy 1 (public; safe to commit):
jq -r '"        - {kty: EC, crv: P-256, kid: \(.kid), x: \(.x), \"y\": \(.y)}"' "public-jwk-$KID.json"
echo "added version $NEW for kid $KID (not pinned)"
```

**Deploy 1: publish the new public key (verifier only).** Values PR: append the printed line under
`consumerDomains.assertion.jwks.keys`, after the current key, and leave `signingKid` at
`$OLD_KID`. Merge, wait for the green `main` run, and tag (packet C-20). The gateway keeps its kid and
key; the domain service restarts with both public keys. Then check that it loads both kids:

```bash
set -euo pipefail
. ./rotation-env.sh; . ./rotation-state.env
kubectl -n "$NS" rollout status deploy/brandme-consumer-domains --timeout=5m
kids=$(kubectl -n "$NS" exec deploy/brandme-consumer-domains -- python -c \
  "import json,os; print(' '.join(sorted(k['kid'] for k in json.loads(os.environ['CONSUMER_DOMAIN_ASSERTION_JWKS'])['keys'])))")
for k in "$OLD_KID" "$NEW_KID"; do
  [[ " $kids " == *" $k "* ]] || { echo "the domain service does not load kid $k" >&2; exit 1; }
done
echo "domain service loads $OLD_KID and $NEW_KID"
```

**Deploy 2: switch the signer.** Values PR: set `signingKid: <NEW_KID>`. Merge, wait for the
green `main` run, and push the tag. While that run waits at the `sandbox` environment approval,
pin the new key and wait for the sync, then approve:

```bash
set -euo pipefail
. ./rotation-env.sh; . ./rotation-state.env
pin "$ID" "$NEW"
wait_synced "$ID" "$NEW"
echo "Secret holds version $NEW: approve the deploy now"
```

The deploy rolls the gateway, because its `CONSUMER_DOMAIN_ASSERTION_KID` changes, and each new
pod starts with the new key and the new kid together. Between `wait_synced` and that rollout, a
gateway pod that restarts for any other reason would pair the new key with the old kid, and the
domain service would refuse its requests until the rollout replaces it. That is why the pin
waits for the approval gate: the window is the few minutes the deploy job needs to reach
`helm upgrade`. If the run fails before `helm upgrade`, pin back (rollback below).

**Verify** after deploy 2:

```bash
set -euo pipefail
. ./rotation-env.sh; . ./rotation-state.env
kubectl -n "$NS" rollout status deploy/brandme-gateway --timeout=5m
same "$(pod_fp brandme-gateway CONSUMER_DOMAIN_ASSERTION_KEY)" "$(sm_fp "$ID" "$NEW")" "gateway key = version $NEW"
kid=$(kubectl -n "$NS" exec deploy/brandme-gateway -- node -e 'process.stdout.write(process.env.CONSUMER_DOMAIN_ASSERTION_KID ?? "")')
[ "$kid" = "$NEW_KID" ] || { echo "the gateway signs with kid '$kid', not $NEW_KID" >&2; exit 1; }
echo "gateway signs with $NEW_KID"
```

Then, with a sandbox test member's session, make one consumer-domain request through the
gateway, `GET /api/v1/me/persona` (`brandme-gateway/src/routes/v1/persona.ts:153`). Expect
200, and no assertion refusal in `kubectl -n "$NS" logs deploy/brandme-consumer-domains`.

**Deploy 3: remove the old public key**, at least 10 minutes after deploy 2. That is well
beyond the 60 s maximum lifetime plus 30 s of skew. Values PR: delete the `$OLD_KID` line from
`consumerDomains.assertion.jwks.keys`; tag. Run the deploy 1 check with only `$NEW_KID`
expected. Then disable the old Secret Manager version
(`gcloud secrets versions disable "$OLD" --secret "$ID" --project "$PROJECT_ID"`) and destroy it
7 days later.

**Rollback:**

- Before deploy 2 is approved: if you pinned already, `pin "$ID" "$OLD"` and
  `wait_synced "$ID" "$OLD"`, then reject the run. Nothing else changed.
- After deploy 2, before deploy 3: `pin "$ID" "$OLD"`, `wait_synced "$ID" "$OLD"`, then
  `helm -n brandme rollback brandme <deploy 1 revision> --wait --timeout 10m` (packet R-3; `helm
  history` lists the revisions). That restores the old kid, and the gateway restarts onto the
  old key. Set `NEW=$OLD` and `NEW_KID=$OLD_KID` in `rotation-state.env`, run the verify block, and
  revert the deploy-2 values PR so the next tag does not switch again.
- After deploy 3: first deploy the old public key again (deploy 1 with the old line), then as
  above.

**Evidence:** kids before and after, versions OLD→NEW, the three deploy run URLs, the persona
request status. Never record a key.

### 5.3 `MIDNIGHT_BLOCKFROST_PROJECT_ID`

The consumer is `brandme-chain` only (rendered chart). The value must match
`^night(preprod|mainnet)[A-Za-z0-9_-]{8,}$` (`brandme-chain/src/midnight/network.ts:36-37`):
`nightpreprod…` for sandbox, `nightmainnet…` for production. The token travels as a URL
query parameter; the Preprod runner redacts it (`brandme-chain/scripts/test-midnight-preprod.mjs:13-15`).
Owner: midnight-rights. Who holds the Blockfrost account is open (packet D7).

**Generate:** create a new project for the right network in the Blockfrost dashboard.
**Store** (pasted without echo, checked before upload):

```bash
set -euo pipefail
. ./rotation-env.sh
ID=brandme-$MODE-rts-midnight-blockfrost-project-id
OLD=$(pinned "$ID"); [[ "$OLD" =~ ^[0-9]+$ ]] || { echo "no pinned version for $ID" >&2; exit 1; }
read -rs BF; [[ "$BF" =~ ^nightpreprod[A-Za-z0-9_-]{8,}$ ]] || { unset BF; echo "not a Preprod project id" >&2; exit 1; }
NEW=$(printf '%s' "$BF" | gcloud secrets versions add "$ID" --project "$PROJECT_ID" --data-file=- --format='value(name)'); unset BF
NEW=${NEW##*/}
printf 'ID=%s OLD=%s NEW=%s\n' "$ID" "$OLD" "$NEW" > rotation-state.env
```

**Pin and restart consumers:**

```bash
set -euo pipefail
. ./rotation-env.sh; . ./rotation-state.env
pin "$ID" "$NEW"
wait_synced "$ID" "$NEW"
kubectl -n "$NS" rollout restart deploy/brandme-chain
kubectl -n "$NS" rollout status deploy/brandme-chain --timeout=5m
```

If the reviewer-gated Preprod run uses the GitHub Environment `sandbox` secret, update it there
too with `gh secret set MIDNIGHT_BLOCKFROST_PROJECT_ID --env sandbox --repo brandmeonline/Brand-Me-Labs`.
That command reads the value from stdin, never from an argument.

**Verify** (all of it before Retire). The capability endpoint alone proves nothing about the
new project id: it is built from configuration and local artifacts and makes no network call
(`brandme-chain/src/routes/midnight.ts:16-18`, `src/midnight/capability.ts:30-81`), so a
well-formed but wrong or revoked id still reads `read_only`. The live check is a GraphQL POST
from the chain pod to the Preprod indexer URL the chain itself builds
(`dist/src/midnight/network.js`, `preprodEndpoints`; source `brandme-chain/src/midnight/network.ts:36-51`),
with the pod's new `MIDNIGHT_BLOCKFROST_PROJECT_ID`. It prints only the HTTP status. Blockfrost
answers 403 to a project id it does not accept (observed 2026-10-30 with a well-formed fake
id); 200 means it accepts this one.

```bash
set -euo pipefail
. ./rotation-env.sh; . ./rotation-state.env
same "$(pod_fp brandme-chain MIDNIGHT_BLOCKFROST_PROJECT_ID)" "$(sm_fp "$ID" "$NEW")" "chain token = version $NEW"
code=$(kubectl -n "$NS" exec deploy/brandme-chain -- node --input-type=module -e '
  import { preprodEndpoints } from "./dist/src/midnight/network.js";
  let out;
  try {
    const r = await fetch(preprodEndpoints(process.env.MIDNIGHT_BLOCKFROST_PROJECT_ID ?? "").indexerHttp, {
      method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ query: "{ __typename }" }),
      redirect: "error", signal: AbortSignal.timeout(15000) });
    out = String(r.status);
  } catch (e) { out = "error " + (e?.cause?.code ?? e?.name ?? "unknown"); }
  process.stdout.write(out);')
[ "$code" = 200 ] || { echo "Preprod indexer answered '$code' to the new project id: do not revoke the old project; roll back" >&2; exit 1; }
echo "Preprod indexer accepts the new project id (HTTP 200)"
kubectl -n "$NS" port-forward deploy/brandme-chain 18082:3001 >/dev/null 2>&1 & pf=$!; trap 'kill "$pf" 2>/dev/null' EXIT; sleep 3
status=$(curl -fsS http://127.0.0.1:18082/midnight/capability | jq -r .status)    # configuration view only
[ "$status" != unavailable ] && echo "capability: $status" || { echo "capability dropped to unavailable" >&2; exit 1; }
```

`pnpm --filter @brandme/chain test:midnight:preprod` behind the Environment reviewer is the
end-to-end check: it submits Preprod transactions with the test wallets (5.4). Run it as well
when the seeds are at hand; it does not replace the probe above. **Rollback:** `pin "$ID" "$OLD"`,
then `wait_synced`, restart and verify; the old Blockfrost project still works until it is
revoked. **Retire:** revoke the old project at Blockfrost only after the verify block above
exits 0, then disable `$OLD`. There is no rollback after the revoke. **Evidence:** the versions,
the probe's HTTP status, the capability status, and the date the old project was revoked.

### 5.4 `MN_PREPROD_SEEDS` (replace and sweep, never edit)

The format is three or more distinct 64-hex seeds, comma-separated
(`brandme-chain/scripts/test-midnight-preprod.mjs:8-9`). Only the Preprod runner
(`pnpm --filter @brandme/chain test:midnight:preprod`) reads them. No runtime service and no
GCP identity ever holds them. Owner: midnight-rights. **Open:** the lane has not named the
wallet tooling, the faucet or the sweep command; until it does, steps 1 and 3 are its to fill in.

1. **Generate:** create three or more new Preprod wallets with the lane's wallet tooling, and
   fund them with tNIGHT and DUST from the Preprod faucet. Record the public addresses only.
2. **Verify the new set before anything else.** Rollback is impossible after the sweep. Run the
   Preprod suite with the new seeds, from stdin, never as an argument:

   ```bash
   set -euo pipefail
   read -rs MN_PREPROD_SEEDS; export MN_PREPROD_SEEDS
   node -e 'const s=process.env.MN_PREPROD_SEEDS.split(",").map(x=>x.trim());
     if(s.length<3||new Set(s).size!==s.length||s.some(x=>!/^[0-9a-f]{64}$/i.test(x)))process.exit(1)'
   read -rs MIDNIGHT_BLOCKFROST_PROJECT_ID; export MIDNIGHT_BLOCKFROST_PROJECT_ID
   pnpm --filter @brandme/chain test:midnight:preprod
   unset MN_PREPROD_SEEDS MIDNIGHT_BLOCKFROST_PROJECT_ID
   ```

3. **Sweep:** move the remaining funds out of the old wallets (the lane's sweep command).
4. **Store:** replace the GitHub Environment secret with
   `gh secret set MN_PREPROD_SEEDS --env sandbox --repo brandmeonline/Brand-Me-Labs` (value from stdin).
5. **Rollback:** before step 3, keep using the old seeds. After step 3, there is none.
   **Evidence:** the new public addresses, the suite result, the sweep transaction ids.

### 5.5 `GCP_SA_KEY`: retire, do not rotate

The only consumer is `build-images` (`.github/workflows/ci-cd.yml:368`), which pushes to
`gcr.io/$GCP_PROJECT_ID` (`:43`). The deploy job already uses Workload Identity Federation.
Which service account backs the key is unverified (packet C-2). Do not create a replacement
key.

1. **Switch** `build-images` to the keyless pusher. Packet gap G24 is the foundation change in
   `ci-cd.yml`: `google-github-actions/auth` with `workload_identity_provider: ${{ vars.BM_GCP_PUSH_WIF_PROVIDER }}`,
   `service_account: ${{ vars.BM_GCP_PUSHER_SA }}`, and `id-token: write` on that job. Set both
   variables from the output of `scripts/provision/gcp-dev-identities.sh` (they are not secrets).
2. **Verify:** one green push to `main` whose "Publish verified images" step pushed all five
   images. Then confirm that the key is unused:

   ```bash
   set -euo pipefail
   . ./rotation-env.sh
   SA=REPLACE_ME_SA_FROM_C2; [[ "$SA" != REPLACE_ME* ]] || { echo "set SA (packet C-2)" >&2; exit 1; }
   gcloud iam service-accounts keys list --iam-account "$SA" --managed-by=user --format='table(name.basename(),validAfterTime,disabled)'
   ```

3. **Disable first** (reversible), then wait for one more green publishing run:

   ```bash
   set -euo pipefail
   . ./rotation-env.sh
   SA=REPLACE_ME_SA_FROM_C2 KEY_ID=REPLACE_ME_KEY_ID; [[ "$SA$KEY_ID" != *REPLACE_ME* ]] || { echo "set SA and KEY_ID" >&2; exit 1; }
   gcloud iam service-accounts keys disable "$KEY_ID" --iam-account "$SA" --project "$PROJECT_ID"
   ```

4. **Delete** the key and the GitHub secret, and delete the manifest row in the same change:

   ```bash
   set -euo pipefail
   . ./rotation-env.sh
   SA=REPLACE_ME_SA_FROM_C2 KEY_ID=REPLACE_ME_KEY_ID; [[ "$SA$KEY_ID" != *REPLACE_ME* ]] || { echo "set SA and KEY_ID" >&2; exit 1; }
   gcloud iam service-accounts keys delete "$KEY_ID" --iam-account "$SA" --project "$PROJECT_ID"
   gh secret delete GCP_SA_KEY --repo brandmeonline/Brand-Me-Labs
   ```

5. **Rollback:** before step 4, run
   `gcloud iam service-accounts keys enable "$KEY_ID" --iam-account "$SA" --project "$PROJECT_ID"`
   and revert the `ci-cd.yml` change. After step 4 there is no rollback; image publishing waits
   for WIF. **Evidence:** the run URL of the green WIF push, the key id disabled and deleted,
   and the dates.

### 5.6 `STRIPE_TEST_WEBHOOK_SECRET` / `_PREVIOUS` (demo/development only)

Both are accepted while set (`stripe_test.py:160-161`), and both must match
`^whsec_[0-9A-Za-z]{16,256}$` (`:57`). The Stripe rail runs only in demo/development
(`brandme_core/domains/commerce/composition.py:42,102-107`). No Stripe webhook route is mounted
on this head, so there is no live endpoint to verify against yet. Owner: commerce-agents.

1. **Generate:** in the Stripe Dashboard (test mode), roll the endpoint's signing secret, and
   keep the old one valid for the overlap Stripe offers.
2. **Store:** in the dev environment's secret settings, set `STRIPE_TEST_WEBHOOK_SECRET_PREVIOUS`
   to the current value, then `STRIPE_TEST_WEBHOOK_SECRET` to the new one. Paste values into the
   settings UI; never into a command line or a chat.
3. **Restart consumers:** restart the dev process that composes the commerce providers (none
   runs as a deployed service).
4. **Verify** (prints a count only; the config also needs `STRIPE_TEST_SECRET_KEY` set):

   ```bash
   set -euo pipefail
   WANT=2   # during the overlap; 1 after the retire step
   n=$(python -c 'import os; from brandme_core.domains.providers.payments.stripe_test import StripeTestConfig
   print(len(StripeTestConfig.from_env(os.environ).webhook_secrets))')
   [ "$n" = "$WANT" ] || { echo "webhook secrets accepted: $n, expected $WANT" >&2; exit 1; }
   echo "webhook secrets accepted: $n"
   ```

   Once a webhook route is mounted, also send a signed test event from the Dashboard and
   expect it to be accepted.
5. **Retire:** after Stripe's overlap ends, clear `STRIPE_TEST_WEBHOOK_SECRET_PREVIOUS`, restart
   again, and run the verify block with `WANT=1`.
6. **Rollback:** during the overlap, swap the two values back. **Evidence:** the date, the
   counts, the endpoint id (not the secret).

### 5.7 `STRIPE_TEST_SECRET_KEY` (demo/development only)

The guard accepts only `sk_test_`/`rk_test_` and refuses live, publishable and webhook values
(`stripe_test.py:56,87-98`). A restricted `rk_test_` key with PaymentIntents write, Refunds
write and Events read is preferred (founder question Q13). Owner: commerce-agents.

1. **Generate:** create a new restricted test-mode key in the Stripe Dashboard. Do not revoke
   the old one yet.
2. **Store:** replace `STRIPE_TEST_SECRET_KEY` in the dev environment's secret settings.
3. **Restart consumers:** the dev process, as in 5.6.
4. **Verify:**

   ```bash
   set -euo pipefail
   python -c 'import os; from brandme_core.domains.providers.payments.stripe_test import require_test_secret_key
   require_test_secret_key(os.environ.get("STRIPE_TEST_SECRET_KEY")); print("test-mode key accepted")'
   python -m pytest tests/test_commerce_stripe_live.py -q -ra   # live test mode; not_run without the key
   ```

5. **Retire:** revoke the old key in the Dashboard after the live suite passes.
6. **Rollback:** until revocation, put the old key back. **Evidence:** the key's Dashboard
   name or id suffix (never the key), and the suite summary.

### 5.8 `BRANDME_DEV_ANTHROPIC_API_KEY` (demo/development only)

A key in sandbox or production refuses to boot (`brandme_core/orchestrator/model_planner.py:277-285`).
Use a dev-workspace key with a monthly cap (founder question Q13). Owner: commerce-agents.

1. **Generate:** create a new key in the Anthropic Console, in the dev workspace.
2. **Store:** replace the value in the dev environment's secret settings. Never name it
   `ANTHROPIC_API_KEY`; app code ignores that name on purpose.
3. **Restart consumers:** the dev process.
4. **Verify:**

   ```bash
   set -euo pipefail
   planner=$(BRANDME_MODE=development python -c 'from brandme_core.orchestrator.model_planner import planner_from_env
   print(type(planner_from_env()).__name__)')
   [ "$planner" = ModelPlanner ] || { echo "planner is '$planner', not ModelPlanner: the key was not accepted" >&2; exit 1; }
   echo "planner: ModelPlanner"
   python -m pytest tests/test_commerce_model_live.py -q -ra            # spends a few tokens; not_run without the key
   ```

5. **Retire:** revoke the old key in the Console. **Rollback:** until revocation, restore the
   old key. **Evidence:** the key name in the Console and the suite summary.

### 5.9 `MAGIC_API_KEY` (developer tooling)

`.mcp.json:9` passes the key on the MCP server's command line, where process listings show
it. Treat it as exposed on any shared machine. It lives in each developer's gitignored
`.claude/.env.local` (template `.claude/.env.local.example:8`), which
`.claude/hooks/session-start.sh` exports. Owner: foundation.

1. **Generate:** create a new key at the provider (21st.dev).
2. **Store:** replace the line in `.claude/.env.local` with an editor. Never commit it.
3. **Restart consumers:** start a new Claude Code session.
4. **Verify:** the `magic` MCP server connects without an authentication error.
5. **Retire:** revoke the old key at the provider. **Rollback:** until revocation, restore the
   old line. **Evidence:** the date only.

### 5.10 What rotation must never touch

- Ingestion cursors.
- The Spanner outbox/inbox.
- The chain operation store.

Rotation only changes credentials. Workloads resume from Spanner state after the restart. Do
not reset reconciliation or replay events as part of a rotation.

## 6. Exposure path (a value was seen where it should not be)

1. **Revoke first, investigate second.** Take whichever applies:
   - disable the exposed Secret Manager version, after pinning back to the previous one (5.1 rollback);
   - regenerate at the provider (Blockfrost, Stripe, Anthropic, 21st.dev);
   - sweep the wallets (seeds);
   - disable and then delete the key (`GCP_SA_KEY`).
2. **Rotate** with the class procedure. For bearer tokens, accept the coordinated restart window.
3. **Treat any committed value as burned**, even after a history rewrite.
   - The repository is public: forks, clones, caches and secret scanners may already hold it.
   - Never "fix" an exposure by force-pushing alone.
4. **Audit:**
   - the Secret Manager data-access audit logs (`AccessSecretVersion`) since the exposure;
   - the provider dashboards;
   - the wallet histories;
   - the GitHub Actions run logs.
5. **Close the hole.** Possible causes:
   - a template carrying a value (`node scripts/check-credential-manifest.mjs` warns on this);
   - a log line;
   - a missing `.gitignore` rule;
   - a token that reached a browser through `NEXT_PUBLIC_` (the checker fails on this).

   Then add a test for it.
6. Record the incident in the evidence log with the timeline and no values.

## 7. Evidence log template (never record a value or a digest)

Store the log next to the deployment evidence. Redact command output down to the status line.

| Date (UTC) | Secret id / credential | Old version | New version | Class | Reason (scheduled / exposure / format change) | Rotator | Approver | Checks run and result (redacted) | Old version disabled / destroyed on |
|---|---|---|---|---|---|---|---|---|---|
| YYYY-MM-DD | brandme-sandbox-rts-chain-service-token | 3 | 4 | internal-bearer | scheduled | name | name | "matches" ×2; chain `/health` 200; gateway `/healthz` 200 | YYYY-MM-DD / YYYY-MM-DD |

## 8. Open items (not done in this change)

- **Secret sync refresh.** How quickly the GKE secret sync add-on refreshes a Kubernetes Secret
  after its SecretProviderClass pin changes is not verified. `wait_synced` fails after 10
  minutes rather than assuming. Whether `versions/latest` falls back when the newest version
  is disabled is also unverified; explicit pins avoid depending on it.
- **`<NAME>_NEXT` dual-accept** (5.1), *proposed, cross-lane (midnight-rights + foundation)*.
- **Startup distinctness** *(proposed)*. The gateway strict-mode guard
  (`brandme-gateway/src/middleware/mode.ts`) should require each `*_SERVICE_TOKEN` whose
  `*_SERVICE_URL` is set, and require all configured tokens to be pairwise distinct. The read
  API should also reject equality with `CHAIN_SERVICE_TOKEN` and `PRIVACY_EXPORT_SERVICE_TOKEN`.
- **Wallet tooling for 5.4.** The midnight-rights lane should name the wallet, faucet and sweep
  commands.
- **Commerce signing key.** `COMMERCE_DOMAIN_ASSERTION_KEY` gets a block when a signer exists.
- **Domain key switch window (5.2).** The kid is a chart value and the key is a synced Secret, so
  deploy 2 has a short window in which a restarting gateway pod pairs the new key with the old
  kid. Carrying the kid in the same Secret as the key (consumer-domains and foundation) would
  remove it.
- **Alerting.** Configure a log-based alert on
  `protoPayload.methodName="google.iam.admin.v1.CreateServiceAccountKey"`, routed to the
  break-glass owner. With `--enforce-no-sa-keys`, `scripts/provision/gcp-dev-identities.sh`
  also enforces `iam.disableServiceAccountKeyCreation`.
- **Legacy deploy script.** `scripts/deploy.sh` still sources `.env.${ENVIRONMENT}`. Retire it
  with the other legacy deploy paths (packet section F).

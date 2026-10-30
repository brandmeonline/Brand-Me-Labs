# Dependency repair verification — 2026-10-23

The previous workspace audit reported 91 findings (13 critical, 31 high, 39 moderate, 8 low). It ran as an informational step in [the PR #45 chain workflow](https://github.com/brandmeonline/Brand-Me-Labs/actions/runs/39873166920), so a green workflow did not mean the dependency audit passed.

## Changes

- Both Next.js apps now pin **15.5.28**, the upstream Maintenance LTS security release, with matching ESLint configuration. React stays at the existing compatible 18.3.1. The console uses the supported top-level `outputFileTracingRoot` setting.
- Vitest, coverage and UI packages pin **3.2.7** across chain/gateway; Tinypool is overridden to **2.1.2** for the worker-options pollution fixes.
- Same-major overrides select PostCSS **8.5.23**, minimatch v9 **9.0.7**, and Babel core **7.29.6**. The gateway uses UUID **11.1.1**, whose upstream exports retain CommonJS support and bundled types.
- `tailwindcss-animate` is a development dependency in both web apps: its only use is in their Tailwind build configuration. This removes build tooling from the declared production dependency set; the full-workspace audit still includes and reports it.
- Both workflows reject any production dependency finding and any critical workspace finding. No advisory IDs are ignored or suppressed. Image publishing waits for the frontend build/audit and the security-scan job, as well as the existing service tests.
- The frontend now has a blocking production-build job. The console image runtime check exercises its packaged native AVIF/WebP codecs before its existing HTTP check.

Upstream references: [Next.js security release](https://nextjs.org/blog/nextjs-security-update-october-14-2026), [Vitest UI advisory](https://github.com/vitest-dev/vitest/security/advisories/GHSA-5xrq-8626-4rwp), [Tinypool advisory](https://github.com/tinylibs/tinypool/security/advisories/GHSA-85c8-ppgw-ccpr), and [UUID CommonJS exports](https://github.com/uuidjs/uuid/blob/v11.1.1/package.json).

## Audit result

`pnpm audit --json` and `pnpm audit --prod --json` were run with pnpm 10.34.6 against the updated workspace lockfile. Counts are a point-in-time registry result, not a guarantee against unknown vulnerabilities.

| Scope | Critical | High | Moderate | Low |
|---|---:|---:|---:|---:|
| Previous workspace | 13 | 31 | 39 | 8 |
| Updated workspace | 0 | 1 | 7 | 0 |
| Updated production dependencies | 0 | 0 | 0 | 0 |

The remaining high finding is [braces stack exhaustion, GHSA-vfj7-8cjw-p6xm](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm). The advisory lists no patched release. The remaining development paths include lint/glob and Tailwind tooling; do not feed them attacker-controlled patterns. It remains visible in the full audit.

The seven moderate findings are development dependencies involving Vitest/mocker ([redirect-mock traversal](https://github.com/advisories/GHSA-82fw-gwwq-j7x9), [manual-mock registration](https://github.com/advisories/GHSA-qxg6-89mg-rqv8)) and [postcss-selector-parser](https://github.com/advisories/GHSA-rj75-hqrm-r3gf). Their fixes require further test-tool/parser upgrades. Do not expose test UI/mock servers to untrusted clients. These findings are not claimed resolved, and the audit has no allowlist hiding them.

## Verification

Both web production builds pass with lint/type validation. Local production servers returned HTTP 200 for all existing console/frontend routes checked, and their linked CSS assets loaded successfully. The console's traced runtime loaded Next.js 15.5.28 and sharp 0.35.5 and encoded AVIF/WebP fixtures successfully. Gateway CommonJS compilation passes.

The patched test runner passed 90 chain/contract tests, 48 gateway tests and 22 real Spanner migration/runtime tests. The PR and post-merge GitHub Actions links record verification of the final published revision, including all five Docker images. The immutable Midnight compiler/runtime/protocol tuple is unchanged; funded Preprod execution and the remaining application integration requirements in `brandme-chain/INTEGRATION.md` remain separate.

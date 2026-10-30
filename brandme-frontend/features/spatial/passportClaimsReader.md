# Passport claims transport

`createPassportClaimsReader()` supplies the claims methods of `ScanConnector`
using the generated `@brandme/contracts` types and the existing same-origin
`GET /api/v1/assets/{uuid}/passport` endpoint. Creation performs no network work.
The app scan route remains unconfigured.

A host with an authoritative resolver can compose it explicitly:

```ts
import { createPassportClaimsReader } from "./passportClaimsReader";
import type { ScanConnector } from "./scanResolution";

const connector: ScanConnector = {
  mode: "development",
  sessionKey, // Host changes this on sign-out, account change or revocation.
  resolve: authoritativeResolver,
  ...createPassportClaimsReader(),
};
```

The host must supply `sessionKey` and `authoritativeResolver`. This module does
not implement tag/photo resolution, infer ownership, activate a route, or define
new facet/value mappings. Do not substitute the legacy intent/commit operation
for a read-only resolver. The optional fetch argument is for trusted tests; do
not inject an authenticated gateway wrapper.

Every public request, including pagination, uses `credentials: "omit"`, so a
signed-in owner's cookie cannot upgrade the response. Only an explicit call to
`unfoldOwnerClaims` uses `credentials: "same-origin"`. Every owner page must say
`viewer: "owner"`; denial or downgrade rejects the whole read. The server still
owns authorization and visibility filtering. The reader cannot establish rights
from a tag, browser state, or arbitrary claim values.

Both methods require an AbortSignal. Requests use GET, same-origin mode,
redirect rejection and `cache: "no-store"`; URLs and headers cannot be configured.
The reader requests up to 24 statements per page and accepts at most 100
statements, five pages, 1 MiB of decoded response bytes in total, and 15 seconds
for the whole operation. Exceeding any limit, a cyclic/invalid cursor, duplicate
claim, invalid response identity, or scope change rejects the entire read. It
returns one complete projection with `next_cursor: null`; it never silently
truncates or returns earlier pages after a later failure. These are scan-client
limits, not new server limits.

The API uses an independent database snapshot for each page; this reader does
not promise a transactionally consistent snapshot across pages. It checks that
asset, viewer, environment and network remain consistent, but a claim could
change on the server between pages. Host session changes must abort outstanding
reads and clear displayed owner data; the existing ScanExperience lifecycle
does this when its connector/sessionKey changes. Keep responses in memory only
and pass them through the existing display adapter. This transport neither
persists nor renders opaque `value` data or `evidence_ref` links. A live scan
demonstration still needs an approved resolver and producer facet mappings.

Contract sources: `packages/contracts/src/read-schemas.json`,
`packages/contracts/generated/api.ts`; pagination and disclosure implementation:
`brandme_core/read_api/app.py` and `brandme_core/read_api/reads.py`.

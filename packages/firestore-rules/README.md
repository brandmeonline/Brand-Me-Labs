# @brandme/firestore-rules

Security rules for the Firestore UI projections written by `brandme_core/events/projections.py`. Spanner is authoritative; projections are disposable, field-minimal read models.

| Path | Who can read | Writes |
|---|---|---|
| `members/{memberId}/**` | the signed-in member whose Firebase uid == `memberId` | never from clients |
| `shared/{shareId}/recipients/{memberId}` | `get` only, by the uid equal to `memberId`, while `expires_at` > now; no `list`. Each recipient has their own copy, so no document reveals the audience | never from clients |
| `projection_tombstones/*`, everything else | nobody | never from clients |

Revocation is a server-side delete of every recipient copy plus a tombstone (`ProjectionStore.apply(Delete(...))`), so the audience loses access immediately and a delayed older update cannot resurrect the share. A copy that someone already downloaded cannot be recalled (spec ch.01 §8).

Server writers use service IAM and bypass these rules. Rules are not a substitute for server authorization (ch.03 §5).

**Open gate:** clients need Firebase Auth custom tokens whose uid is the internal `member_id`. The gateway does not mint them yet.

## Tests

```bash
python scripts/python/fetch_firestore_emulator.py          # pinned 1.22.0, SHA-256 verified; needs Java
.cache/firestore-emulator/platform/cloud-firestore-emulator/cloud_firestore_emulator start --host=127.0.0.1 --port=8080 &
FIRESTORE_EMULATOR_HOST=127.0.0.1:8080 pnpm --filter @brandme/firestore-rules test
```

The suite skips (and says so) without an emulator. With `BRANDME_REQUIRE_EMULATORS=1` (CI) it fails instead, and CI also fails on any skip or a zero pass count. As a negative control, an allow-all rules file fails 5 of the 6 tests.

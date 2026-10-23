# Durable event delivery

The Spanner outbox has a runnable Pub/Sub dispatcher. Domain changes and events
commit together; publishing happens outside the transaction. An event becomes
`delivered` only after a valid broker acknowledgement. That means **accepted by
the broker**, not that a consumer applied a business effect.

## Configure and run

1. Apply migrations through **V013**. Startup checks the ledger and actual dispatch
   index. Stop older dispatchers before rolling out the new lease semantics.
2. Set `BRANDME_MODE` and `ENVIRONMENT` to the same explicit value, plus
   `SPANNER_PROJECT_ID`, `SPANNER_INSTANCE_ID`, and `SPANNER_DATABASE_ID`. Use
   separate databases and workload identities per deployed environment.
3. Provision three distinct Pub/Sub topics and authorized subscriptions. Configure
   `OUTBOX_PUBSUB_TOPIC_PUBLIC`, `OUTBOX_PUBSUB_TOPIC_MEMBER_PRIVATE`, and
   `OUTBOX_PUBSUB_TOPIC_RESTRICTED` with full `projects/PROJECT/topics/TOPIC` names.
   Every topic name must start with `brandme-ENVIRONMENT-`.
4. All three topics are **private infrastructure**. Even public-class envelopes
   carry internal actor/correlation references: never expose them directly to
   browsers, public subscribers or analytics. Separate their IAM policies. Create
   subscriptions before publishing and enable at least **24 hours of topic
   retention** (`messageRetentionDuration: "86400s"`). Startup refuses topics
   without this recovery window; broker acceptance alone does not guarantee
   future consumption. Configure retention and
   subscription retry/dead-letter policies for the data being processed.
5. Sandbox/production use Application Default Credentials from the workload
   service identity. Grant `pubsub.topics.publish` and `pubsub.topics.get` on only
   these topics, plus required Spanner data permissions. Both emulator settings
   are rejected in these modes. No credentials belong in source or reports.
6. Demo/development require **both** `SPANNER_EMULATOR_HOST` and
   `PUBSUB_EMULATOR_HOST`. Pub/Sub accepts loopback or the private container names
   `pubsub` / `pubsub-emulator`. The worker never creates topics/subscriptions.
7. Run `python -m brandme_core.events.worker --check`, then
   `python -m brandme_core.events.worker`. `--once` processes at most 50 events,
   exiting nonzero for failed/dead/stale outcomes. The existing core image includes
   this module: override its entrypoint/command with the same Python invocation
   and disable its legacy HTTP healthcheck for the worker. No target deployment
   or migration is performed by this code change.

The default allowlist is the closed catalog in `brandme_core/domains/events.py`:
identity/session/consent, rights/chain projection, and privacy deletion contracts.
`OUTBOX_EVENT_TYPES` can restrict it with an exact comma-separated subset.
Unsupported types stay pending for their owning domain. The separate persona and
commerce implementations still need catalog alignment and real subscribers.

## Recovery and privacy

- Each claim selects one due event in one environment, with a fresh random token
  and database-clock 30-second lease. No waiting batch is leased in advance. Polls
  rotate shards, process at most 50 claims, and wait two seconds. SIGTERM stops new
  claims and finishes current work.
- Expired workers cannot finish replacement leases. Attempts count at claim,
  including crashes. Persisted exponential jitter caps at five minutes and ten
  attempts. Invalid payloads become dead letters without transmission; unknown
  types remain pending. Retry records contain fixed codes, never exception text.
- Lost acknowledgements can republish the same application `event_id`. Pub/Sub
  assigns a new `messageId`: consumers must deduplicate the application ID with
  `first_delivery` in the **same transaction as their effects**, then acknowledge
  the subscription after commit. Recheck current authorization/deletion freezes
  before effects, and validate the closed envelope, expected environment and
  privacy class at ingress. Handle out-of-order aggregate versions. There is no distributed
  exactly-once claim or automatic dead-letter replay.
- Closed payload validation runs before transport. Events cap at 256 KiB and
  broker replies at 16 KiB; redirects and ambient proxies are disabled. Requests
  and credential refresh use a five-second timeout. Logs exclude raw payloads,
  exception bodies, URLs, member IDs and event IDs.
- Monitor pending age, dead count, lease recovery and `dispatch_unavailable` logs.
  Database-wide failures back off with jitter to one minute; idle polls do not log.
  Investigate current policy before replay. Broker retention, subscriptions,
  authenticated business handlers and cloud alerting remain deployment work.

## Verification

`python scripts/python/fetch_pubsub_emulator.py` fetches Google's **0.8.37**
component with its published SHA256 (Cloud SDK 590.0.0 manifest). Java 17+ is
required. With a running Spanner emulator:

```sh
SPANNER_EMULATOR_HOST=127.0.0.1:9010 \
PUBSUB_EMULATOR_BIN=.cache/pubsub-emulator/platform/pubsub-emulator/bin/cloud-pubsub-emulator \
python -m pytest tests/foundation/test_outbox_emulator.py tests/foundation/test_outbox_delivery.py -q
```

Tests exercise actual Spanner migrations and a real local Pub/Sub process,
publish/pull, lost acknowledgement, atomic inbox dedupe, lease races, crash
recovery, malformed payloads, environment isolation and a separately started
worker with SIGTERM shutdown. The blocking core CI job requires the pinned
emulator. Emulator evidence does not verify cloud IAM, target deployment or
funded Midnight transactions.

Primary references: [publish API](https://cloud.google.com/pubsub/docs/reference/rest/v1/projects.topics/publish),
[emulator](https://cloud.google.com/pubsub/docs/emulator),
[authentication transport](https://googleapis.dev/python/google-auth/latest/reference/google.auth.transport.requests.html).

## Firestore projections

`brandme_core/events/projections.py` turns committed events into Firestore read models for timely UI updates (spec ch.03 §5):

- **Spec.** `ProjectionSpec(name, audience, path_template, allowed_fields)` declares one document kind. Member-private kinds live under `members/{member_id}/`, shared kinds under `shared/{share_id}`. Shared specs and documents reject private field names (owner/member refs, body data, prices, receipts, wallet/ownership history, persona vectors), including nested ones.
- **Monotonic.** `ProjectionStore.apply(Upsert(...))` writes only when `source_version` is newer than the stored document and any tombstone. Redelivery and out-of-order events are no-ops (`stale` / `revoked`).
- **Revocation.** `Delete(...)` removes the document and records a tombstone, so older updates cannot resurrect it. A delete older than the current view is ignored (`stale`), so a later re-share stays intact.
- **Deletion.** `purge_member(member_id)` removes every private projection (for privacy deletion jobs).
- **Reducers.** Register pure reducers per event type (`ProjectionRegistry.register`); they return ops and never write. Apply them from a Pub/Sub subscriber after the usual `first_delivery` dedupe.

Client access is defined in `packages/firestore-rules`. Tests: `tests/foundation/test_projections_emulator.py` (needs `FIRESTORE_EMULATOR_HOST`).

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

## Event catalogs

The default allowlist is every contract registered by the closed catalog list in
`brandme_core/events/catalogs.py`, loaded by `WorkerConfig.from_env` after the
mode guard:

| Lane | Catalog module | Contracts |
|---|---|---|
| foundation | `brandme_core.domains.events` | 11: identity/session/consent, rights/chain projection, privacy deletion |
| consumer-domains | `brandme_core.domains.persona.lane`, then `load_domains()` | 36: persona, wardrobe, social, rewards, media |
| commerce-agents | `brandme_core.domains.commerce.events` | 6 on PR #51; `absent` on main until it merges |

`OUTBOX_EVENT_TYPES` can restrict the allowlist with an exact comma-separated
subset. Types no catalog registers stay pending. The ready line reports each
lane's catalog as `loaded` or `absent`. Pub/Sub topics stay per privacy class;
subscribers filter by the `event_type` attribute.

- **Adding a catalog** is a foundation PR: add a `Catalog` entry, pin its
  contract count in `tests/foundation/test_outbox_lane_catalogs.py`, and keep the
  module importable without services, providers or credentials. Nothing is read
  from the environment. A lane needs no private worker:
  `brandme_core/domains/persona/outbox_worker.py` is now redundant.
- **`absent`** applies only to an entry with `until_merged` whose module does not
  exist at all. Any other failure (a missing required module, an import error in
  a present module, a failing loader) refuses startup with exit 2 and
  `{"status":"startup_refused","reason":"event_catalog_unavailable","lane":LANE}`.
  The import error's text is not logged. Delete `until_merged` once the lane's PR
  merges.
- **Version rollout.** The dispatcher claims rows by `event_type` name only
  (`outbox.py:112-115`), while the registry is keyed by `(event_type,
  schema_version)`. A row at a version this worker image has not registered is
  dead-lettered as `invalid_event`, not left pending (`outbox.py:201-204`). Ship
  each new contract version in the worker image before any writer emits it.

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

- **Spec.** `ProjectionSpec(name, audience, path_template, allowed_fields)` declares one document kind. Member-private kinds live under `members/{member_id}/`. Shared kinds use exactly `shared/{share_id}`.
- **Full snapshots.** `Upsert` replaces the whole view at `source_version`. Reducers build it from authoritative state, never as a delta, so a skipped version cannot leave a view incomplete.
- **Monotonic.** Writes apply only when newer than the stored view and any tombstone. Redelivery and out-of-order events return `stale` or `revoked`.
- **Shared views per recipient.** Each share is written as `shared/{share_id}/recipients/{member_id}`, one copy per audience member. Copies carry no audience list or member IDs. Removing a member from the audience deletes their copy.
- **Private-field refusal.** Shared specs and documents reject private names in any style. Keys are normalized and checked against stems: owner, member, wallet, body, price, address, audience and similar. Nested keys are checked too.
- **Expiry.** `expires_at` must be timezone-aware.
- **Revocation.** `Delete(...)` removes every copy and records a tombstone, so older updates cannot resurrect the share. A delete older than the current view is ignored (`stale`).
- **Member deletion.** `purge_member(member_id)` first writes a member-wide marker and then removes every private projection. Later upserts for that member return `revoked`.
- **Reducers.** Register pure reducers per event type (`ProjectionRegistry.register`) and apply them after `first_delivery` dedupe.

Client access is defined in `packages/firestore-rules`. Tests: `tests/foundation/test_projections_emulator.py` (needs `FIRESTORE_EMULATOR_HOST`).

## Retention and erasure

Founder ruling Q19 (the "Q9 purge"). `retention.py` holds the Spanner logic and
the job; `erasure.py` connects it to My Data. No migration is needed: the purge
uses the V013 index `OutboxByEnvironmentStatus`.

- **Delivered rows.** `python -m brandme_core.events.retention --once` runs
  hourly (CronJob `events-retention` in `brandme-infra/helm/brandme`, its own
  audited process `events_retention`). It deletes delivered rows 7 days after
  delivery, for its own environment, shard by shard. Pending, leased and
  ordinary dead letters are never purged by age; their retention is still open.
  `--check` verifies schema and configuration. Refusals print constant records
  and logs carry counts only, never event, member or subject IDs.
- **Account deletion.** Foundation owns the table, so it registers two
  categories: `platform.event_outbox` and `platform.request_replay`. They go
  into the privacy lane's default registry and `data_categories()` when
  `brandme_core.domains` is imported. A composition that builds its own
  `PrivacyRegistry` calls `register_platform_privacy(reg)`. A row names the
  subject when its `aggregate_id`, its actor (`member:<id>` or a delegation of
  it) or an exact JSON string token in its payload is the subject. That
  includes other members' events about them; short refs never match by
  substring. Undelivered rows are withdrawn in place: status `dead`,
  `last_error = 'subject_erased'`, payload `{}`, neutral actor, aggregate and
  correlation. Delivered rows are deleted. A withdrawn row fails closed-schema
  validation and is never claimed again; a lease in flight finishes `stale`.
  Withdrawn rows are purged 7 days after withdrawal.
- **Replay records.** The subject's `IdempotencyRecords` (principal
  `member:<id>` and its delegations) are deleted. In other members' saved
  responses, the subject's ID is replaced by the nil member, so their retries
  still replay instead of running twice. `expires_at` is not enforced yet:
  expired records are not purged.
- **Backstop.** Each pass re-erases subjects whose platform categories were
  tombstoned in the last 30 days. That catches late writes by writers that are
  not freeze-guarded (the gateway's session store) and events written after the
  platform step of a deletion. Restore re-applies the same erasure
  (`reapply_tombstones_after_restore`).
- **Not recalled.** Copies already accepted by Pub/Sub stay until topic and
  subscription retention expire (24 hours or more). Consumers must recheck
  deletion freezes before effects (see "Recovery and privacy").
- **Scale.** Erasure scans whole tables with partitioned DML, a few statements
  per 100 subject keys. When the 7-day outbox outgrows an hourly scan, add a
  subject index (for example a child table written with each event) in a
  migration after V015.
- **Out of scope.** No handler erases the identity tables yet (`Members`,
  `MemberSettings`, `MemberIdentities`, `ConsentGrants`, `Sessions`). Whether to
  erase them is an open founder question.

Tests (Spanner emulator): `tests/foundation/test_outbox_retention.py` and
`tests/foundation/test_deletion_leaves_no_member_rows.py`. The second runs a
real account deletion over the consumer-domains seed. It traces every column of
every table and finds no outbox or replay row naming the member, on the
delivered and undelivered paths. Without the platform handler, the same trace
finds at least 21 outbox rows.

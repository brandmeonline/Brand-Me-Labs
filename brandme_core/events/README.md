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
| consumer-domains | `brandme_core.domains.persona.lane`, then `load_domains()` | 37: persona, wardrobe, social, rewards, media |
| commerce-agents | `brandme_core.domains.commerce.events` | 7: delegation (created, revoked, boundary changed), quote, purchase approval/authorization, order observation |

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
  exist at all. No entry on main sets it: every listed catalog must load. Any
  other failure (a missing required module, an import error in a present module
  such as a missing dependency, or a failing loader) refuses startup with exit 2 and
  `{"status":"startup_refused","reason":"event_catalog_unavailable","lane":LANE}`.
  The import error's text is not logged. A new lane's entry may set
  `until_merged` while its PR is open, provided its parent package already exists
  on main (`find_spec` imports the parent; a missing parent refuses); delete it when
  the PR merges. `test_every_shipped_catalog_is_required` fails while any shipped
  entry still sets it.
- **Pending backlog.** Rows of a type no catalog registered stay pending, so the
  first rollout of a worker image that adds a catalog publishes every such row
  already in the database (`outbox.py:112-115`). No tool removes pending rows by
  type: the hourly job purges only delivered rows and erased tombstones
  (`retention.py:262`), and account deletion withdraws only that subject's own
  rows. So before pointing a new worker image at a long-lived database, either
  accept that the backlog is published (consumers must already handle replays and
  check freezes) or dead-letter those rows with a reviewed one-off statement. Today
  no long-lived database exists (nothing is deployed).
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
python -m pytest tests/foundation/test_outbox_emulator.py tests/foundation/test_outbox_delivery.py \
  tests/foundation/test_outbox_lane_catalogs.py -q
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
  delivery, for its own environment, shard by shard. Pending and leased rows
  are never purged by age. Ordinary dead letters (`invalid_event`,
  `message_rejected`, `delivery_attempts_exhausted`) keep their full payload
  until operators resolve them or the member deletes their account; an age
  limit for them is still open. `--check` verifies schema and configuration.
  Refusals print constant records and logs carry counts only, never event,
  member or subject IDs.
- **Account deletion only.** Foundation owns the tables, so it registers two
  categories: `platform.event_outbox` and `platform.request_replay`. They go
  into the privacy lane's default registry and `data_categories()` when
  `brandme_core.domains` is imported. A composition that builds its own
  `PrivacyRegistry` calls `register_platform_privacy(reg)`. Both categories
  hold what an active account needs (undelivered changes, replay protection),
  so they are erased only by a deletion job with scope `account`. The handler
  refuses three requests truthfully and changes nothing: a category-only
  request, a record-level request, and a subject ref the platform cannot match
  safely (outside `[A-Za-z0-9._:@/+-]{1,128}`). It returns the lanes' refusal
  shape (`done=True` with an exception reason) and never raises, so the job's
  other categories still run. The category text tells members this. A restore
  that carries `DeletionJobs` with the tombstones re-applies a refused tombstone
  as a no-op. The `data_categories()` delete callbacks, which only
  `bridge_foundation_categories` would call, raise: that path always reports
  "deleted" and cannot report a refusal or a count, so a job composed through it
  fails loudly. Compositions use `register_platform_privacy`.
- **The member's own events.** An event is the subject's own when its
  `aggregate_id` or its actor (`member:<id>` or a delegation of it) is the
  subject. Undelivered ones are withdrawn in place: status `dead`,
  `last_error = 'subject_erased'`, payload `{}`, neutral actor, aggregate and
  correlation. Delivered ones are deleted. A withdrawn row fails closed-schema
  validation and is never claimed again, and a lease in flight finishes
  `stale`. Withdrawn rows are purged 7 days after withdrawal.
- **Everyone else's events.** Other members' and services' events that name
  the subject keep their row and status, whether delivered or not. Each JSON
  string value equal to the subject (`<id>` or `member:<id>`) becomes the nil
  member (`00000000-0000-0000-0000-000000000000`, same form), so their side
  effects survive. For example, decision.closed still credits the other
  respondents, because the rewards consumer skips the nil member
  (`domains/rewards/consumer.py:73-75`). Only whole values change: object keys
  are never rewritten (two erased keys would collapse into one), short refs
  never match by substring, and a list keeps one nil member, so unique-id lists
  stay valid. No registered contract keys a payload by member id. Every
  contract with a member-id field still validates after unlinking (the nil
  member passes `format: uuid`). Unlinked delivered rows age out with the
  7-day purge.
- **Replay records.** The subject's `IdempotencyRecords` (principal
  `member:<id>` and its delegations) are deleted. Other members' saved
  responses are unlinked the same way, so their retries still replay instead
  of running twice. `expires_at` is not enforced yet: expired records are not
  purged.
- **Backstop.** Each pass re-erases subjects whose platform categories were
  tombstoned by an account deletion (a join on `DeletionJobs.scope =
  'account'`) in the last 30 days. That catches late writes by writers that are
  not freeze-guarded (the gateway's session store) and events written after the
  platform step of a deletion. A category-only request is never swept.
- **Restore.** `reapply_tombstones_after_restore` re-applies the same erasure.
  The scope comes from `DeletionJobs`, which the tombstone does not record:
  every category of a job gets a tombstone, refused ones included
  (`domains/privacy/privacy.py:307-308`). A restore that carried only
  `DeletionTombstones` has no job row, and then privacy wins: the tombstone is
  re-applied as an erasure and the restore completes. The cost is that a refused
  category-only request on a still-active member, restored this way, also erases
  that member's undelivered events and replay records. Carry `DeletionJobs` (and
  `DeletionSteps`) with the tombstones to keep refusals as no-ops.
- **Not recalled.** A delivery already in flight when the deletion runs can
  still reach the broker. The dispatcher read the payload when it claimed the
  row, and publishes it before its `stale` finish. Copies accepted by Pub/Sub
  stay until topic and subscription retention expire (24 hours or more), even
  after the receipt says the category was deleted. Consumers must recheck
  deletion freezes before acting (see "Recovery and privacy"). The receipt
  itself does not say this: the orchestrator drops the `purge_derived` detail
  (`domains/privacy/privacy.py:378-407`), and returning it as an exception would
  block every restore (`:456-458`). The disclosure is in the category's
  member-facing retention text; surfacing derived detail in receipts is the
  privacy lane's change.
- **Scale.** Erasure scans whole tables: partitioned DML for the subject's own
  rows, and a snapshot prefilter plus compare-and-set updates (100 rows per
  transaction) for unlinking. That is a few statements per 100 subject keys.
  When the 7-day outbox outgrows an hourly scan, add a subject index in a
  migration after V015 (for example, a child table written with each event).
- **Out of scope.** No handler erases the identity tables yet (`Members`,
  `MemberSettings`, `MemberIdentities`, `ConsentGrants`, `Sessions`). Whether to
  erase them is an open founder question.

Tests (Spanner emulator): `tests/foundation/test_outbox_retention.py` and
`tests/foundation/test_deletion_leaves_no_member_rows.py`. The second is the
joint proof with the privacy orchestrator (`MyDataService.request_deletion` and
`run_deletion`). It runs a real account deletion over the consumer-domains
seed, then traces every column of every table. No outbox or replay row names
the member on either the delivered or the undelivered path. Other members' rows
survive with the member unlinked, and the friend's decision still credits the
other respondent. Without the platform handler, the same trace finds at least
21 outbox rows.

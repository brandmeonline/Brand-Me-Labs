# My Data orchestration

`MyDataService` is a Python orchestration library over the V009 Spanner tables.
The gateway routes under `/api/v1/me` enforce a verified member principal,
`privacy:manage`, and recent `auth_time` for export and deletion. A deployed,
authenticated backend behind those routes is **still required**. Do not expose
these library methods directly to callers or accept a caller-supplied subject.

## Current behavior

- The inventory describes the categories actually registered in `PrivacyRegistry`.
  An empty registry, empty selection, duplicate selection or unknown category
  cannot create an export or deletion job. A nonempty registry alone is **not**
  evidence that all account data has been registered.
- Export requires reauthentication within ten minutes, reads registered handlers,
  rejects credential keys in snake_case/camelCase/hyphenated spelling, and records
  an object digest and expiry. The object key is `exports/<job_id>.json`, without
  a subject identifier. Handler or upload errors record a generic failed job and
  attempt object cleanup; `manifest_json.cleanup = "required"` means cleanup
  remains outstanding. Raw provider exceptions are not stored or returned.
- A lost database acknowledgement during finalization returns
  `export_finalization_unconfirmed`. It does not delete a possibly committed
  ready object's bytes. Resolve the durable job state before retrying or cleaning
  up; a database outage can leave a running job and an orphaned private object.
- Deletion acceptance commits the job, steps, processing freeze and registered
  domain event in one transaction. Existing consent/restriction freezes are
  preserved. Records and derived cleanup must both finish before completion.
  An outcome with `done=False` remains pending even if it includes an exception.
- Retries preserve committed row counts and terminal exceptions, and skip finished
  steps. Category freezes are released only after **every** overlapping deletion
  has completed, in either completion order. Failed jobs remain blockers. Account
  freezes remain permanent. Receipts describe any restriction still active at
  completion; historical receipts are not rewritten after later jobs finish.

Stop older privacy executors before upgrading. Confirmed terminal exceptions now
use `DeletionSteps.state = "exception_done"` (within the existing V009 column).
The older `exception` state did not distinguish finished from unfinished work;
unfinished jobs with that state recheck their handler instead of assuming completion.
Already completed historical jobs are not rewritten and need separate review if
they were processed by an older executor.

## Restore and recovery

1. Stop member traffic, all writers and deletion execution before restoring. This
   library is not a distributed traffic switch. Ensure the authoritative tombstone
   ledger survives outside the backup being restored; an old backup alone cannot
   contain deletions accepted after that backup.
2. Run `reapply_tombstones_after_restore(backup_ref, backup_taken_at)`. It records
   a durable `restoring` barrier before invoking handlers. Native transactional
   handlers must raise if record removal is unfinished; their count must be a
   nonnegative integer. Outside-transaction adapters must return a valid, finished
   `DeletionOutcome` without an exception. Derived cleanup has the same requirement.
3. On interruption or failure, `RestoreNotServing.restore_id` identifies the run.
   Keep traffic stopped. Fix the underlying failure and resume with that ID and
   the exact same backup reference and timestamp. Reapplication is idempotent and
   reruns all preserved tombstones. It does not create another unresolved barrier.
4. Only `tombstones_reapplied` and `serving` states pass `assert_serving()`. Failed,
   interrupted and unknown states block it. Export, deletion acceptance and deletion
   execution also check this barrier. Missing handlers, unfinished cleanup and
   invalid outcomes never mark a restore complete.
5. Call `assert_serving()` and verify the other services' restore gates before
   reopening traffic. Each **new physical restore** requires a new run; a completed
   run cannot be reused for a later restore of the same backup.

## Handler and deployment requirements still open

`run_deletion` requires one executor per subject. External callbacks must be
idempotent, and the caller must serialize them; no recoverable distributed lease
or authenticated deletion consumer is supplied by this library. Do not connect
an at-least-once Pub/Sub delivery directly to this method. The outbox's publisher
lease protects event delivery, not these external deletion effects.

Complete the domain catalog and register real handlers before accepting full
account deletion. The native rights handler covers control links, operation
history, transfers, reprint jobs and non-erasable ledger references. The persona
handler in `tests/fixtures/privacy` is a test fixture. Foundation adapters depend
on the owning domain's export/delete callbacks; a bridge is not proof of coverage.

The backend still needs subject-authorized export/status/download access, private
object storage with expiry and orphan cleanup, bounded export work, idempotent
request acceptance, serialized durable deletion execution and all domain writers'
transactional `assert_processing_allowed` checks. The configured backup retention
must match infrastructure policy before receipts are served to members. Library
exports include internal storage references; the HTTP boundary must not relay
them as public download URLs.

## Verification

`tests/test_privacy.py`, `tests/test_privacy_recovery.py` and `tests/test_rights.py`
exercise real GoogleSQL and transaction rollback on the pinned Spanner emulator.
The main CI core job requires that emulator and runs all three suites. Coverage
includes overlapping deletion completion, pending records/derived data, preserved
exceptions and counts, independent restrictions, failed uploads and lost commit
acknowledgements, malformed outcomes, restore gating and resuming a specific run.
These tests do not demonstrate a cloud deployment or completed member deletion.

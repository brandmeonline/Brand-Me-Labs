# Private known-garment evidence intake

`fit-evidence-private.mjs` evaluates **supplied physical-garment records** with the
same `fitEvidence.ts` evaluator used by the application tests. It does not collect
measurements, reconstruct geometry, validate a provider, or verify that a physical
session took place. Every report retains `INPUTS_RECORDED_UNVERIFIED` and
`calibratedFitAvailable: false`.

Use the pinned Node version in `.nvmrc` after the normal frozen workspace install.
Prepare an existing, private directory outside every Git checkout/worktree and choose
two distinct absolute `.json` paths. Neither path may contain a symbolic link,
Windows junction, parent traversal, network/device namespace, or alternate data
stream. The input must be a regular file with one hard link. The command creates no
directories and never replaces an existing output.

```powershell
node scripts/assets/fit-evidence-private.mjs --input C:\BrandMePrivate\known-garments.json --output C:\BrandMePrivate\report-001.json
```

On POSIX systems, supply equivalent absolute paths in your private directory. Use
canonical paths: a symlinked parent directory is rejected even if its target is
outside a repository. Keep the input, private method record, and output together
under your own retention/access policy. Nothing is uploaded or committed by this
command.

## Prepare actual records

Follow the lane's physical garment session protocol before assembling the input.
This intake handles **garment chest/waist/hip circumference comparisons only**;
the separate 18 body readings do not belong in this dataset.
Keep the operator/session details, instrument and resolution, garment identity and
revision, reference procedure, repeated readings, uncertainty calculation, and
estimate method/model revision in a separate **private method record**. Assign
opaque references to that record and the garments; use no names, contact details,
account identifiers, or file paths as references.

The input is UTF-8 JSON, at most **4 MiB**, with exactly the existing evaluator's
fields below. Unknown fields, duplicate JSON object keys, unsupported values,
duplicate fixture IDs, and repeated garment/dimension pairs are rejected.

| Location | Required value |
| --- | --- |
| `schemaVersion` | `"garment-dimension-evidence-v1"` |
| `kind` | `"physical-garment"`; synthetic datasets are refused |
| `protocol.referenceMethod` | Opaque reference to the actual reference measurement procedure |
| `protocol.estimateMethod` | Opaque reference to the actual estimate procedure/model |
| `protocol.revision` | Opaque method revision reference |
| `protocol.evidenceRef` | Opaque reference to the private session/method record |
| `points` | Array of 1–10,000 distinct garment/dimension comparisons |
| Each point's `fixtureId` | Unique opaque comparison reference |
| Each point's `garmentRef` | Opaque garment reference, shared only by that garment's dimensions |
| Each point's `dimension` | `"chest"`, `"waist"`, or `"hip"` |
| Each point's `referenceCm`, `estimateCm` | Finite numbers from 20 through 300, in centimeters |
| Each point's `referenceUncertaintyCm` | Finite number from 0 through 20, backed by the private method record |

References use the existing schema's 1–128 character format: an ASCII letter/digit
first, then letters, digits, `.`, `_`, `:`, or `-`. All fields are mandatory. Body
measurements, photographs, subject records, and free-form notes are unsupported.
Compare the same documented garment circumference and units. Do not relabel flat
width, hem, shoulder, or length readings as supported circumferences. Estimates
must come from a documented independent method and revision, not copies of the
reference measurements. This command introduces no estimation engine and cannot
establish that the supplied methods are independent. Combine repeated tape readings
by the documented procedure before
reporting a garment/dimension once; repeats do not create independent samples.
Do not relabel arithmetic fixtures as physical evidence to exercise this command.

## Read the private report

The report contains aggregate counts, signed bias, MAE, RMSE, maximum absolute
error, and mean reference uncertainty. It includes no individual measurement,
fixture/garment identifier, input path, or original protocol label. Method,
revision, and evidence references are encoded as `sha256:` plus the SHA-256 of the
exact original UTF-8 value; resolve them using the private input/method record.
Provenance also hashes the exact input bytes, evaluator source, and intake source.
Hashes identify bytes and do **not** establish authority, consent, or independent
verification.

The report is still private. Hashed references are pseudonymous and linkable, and
guessable labels may be recoverable. Small-sample aggregates can also be revealing.
Review and authorize any sharing separately; this tool provides no anonymization
guarantee. These physical comparison numbers do not establish fit accuracy;
dimensional error alone does not validate sizing, comfort, drape, or fit.

Success prints only a fixed status, report hash, and `calibratedFitAvailable: false`.
Failures print a fixed error code/message without input contents or paths. A report
is created exclusively with POSIX mode `0600`; on Windows, the inherited directory
ACL determines access, and that mode does not guarantee private ACLs. The tool does
not change existing directory permissions or ACLs. Choose a directory already
restricted to the intended operator.

Path checks reject existing symlinks/junctions and recheck directory/file identity
around intake/output creation. They are not a race-proof filesystem sandbox: use
trusted private directories and stop processes that could rename directories,
replace links, or mutate input files during the run. If a write fails, inspect the
chosen output location before retrying; cleanup will not follow a moved path.

## Functional checks

```text
node --test scripts/assets/tests/fit-evidence-private.test.mjs
```

These checks use invented temporary inputs solely to test the physical-input code
path. They verify metrics/provenance and privacy, malformed UTF-8 and duplicate keys,
schema/count limits, no overwrite (including competing writers), repository/path
boundaries, and real directory symlinks/junctions and hard links. Temporary reports
are removed. Test success is not physical measurement evidence.

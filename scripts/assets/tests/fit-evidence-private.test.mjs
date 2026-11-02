import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, mkdir, writeFile, readFile, stat, rm, realpath, symlink, link, access } from "node:fs/promises";
import { createHash, randomUUID } from "node:crypto";
import { spawnSync } from "node:child_process";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const repository = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const cli = path.join(repository, "scripts/assets/fit-evidence-private.mjs");
const hash = (value) => createHash("sha256").update(value).digest("hex");
const absent = async (file) => assert.rejects(access(file), { code: "ENOENT" });

// Invented records exercise the physical-input branch only. They are never saved as
// repository evidence and cannot establish that a physical measurement happened.
const example = () => ({
  schemaVersion: "garment-dimension-evidence-v1",
  kind: "physical-garment",
  protocol: {
    referenceMethod: "private-reference-person-marker",
    estimateMethod: "private-estimate-person-marker",
    revision: "private-revision-marker",
    evidenceRef: "private-session-marker",
  },
  points: [
    { fixtureId: "private-fixture-a", garmentRef: "private-garment-a", dimension: "chest", referenceCm: 111.237, referenceUncertaintyCm: 0.5, estimateCm: 113.237 },
    { fixtureId: "private-fixture-b", garmentRef: "private-garment-a", dimension: "waist", referenceCm: 84.791, referenceUncertaintyCm: 0.5, estimateCm: 82.791 },
    { fixtureId: "private-fixture-c", garmentRef: "private-garment-b", dimension: "hip", referenceCm: 109.369, referenceUncertaintyCm: 0.5, estimateCm: 110.369 },
  ],
});

async function workspace(t) {
  const base = await realpath(tmpdir());
  const directory = await mkdtemp(path.join(base, "brandme-fit-private-"));
  t.after(async () => {
    // Verify the absolute recursive-delete target stays in the dedicated temp root.
    assert.equal(path.dirname(directory), base);
    assert.ok(path.basename(directory).startsWith("brandme-fit-private-"));
    assert.equal(await realpath(directory), directory);
    await rm(directory, { recursive: true, force: true });
  });
  const input = path.join(directory, "private-input.json");
  const output = path.join(directory, "private-report.json");
  return { directory, input, output };
}

function invoke(input, output, args) {
  const result = spawnSync(process.execPath, [cli, ...(args ?? ["--input", input, "--output", output])], {
    cwd: repository, encoding: "utf8", maxBuffer: 512 * 1024, timeout: 20_000,
  });
  assert.equal(result.error, undefined);
  assert.equal(result.signal, null);
  return result;
}

function rejected(result, code) {
  assert.equal(result.status, 1);
  assert.equal(result.stdout, "");
  const error = JSON.parse(result.stderr);
  assert.equal(error.status, "REJECTED");
  assert.equal(error.code, code);
  assert.deepEqual(Object.keys(error).sort(), ["code", "message", "status"]);
  assert.doesNotMatch(result.stderr, /private-(?:input|fixture|garment|session|reference|estimate|revision)|111\.237|113\.237|at .*\.mjs/);
}

test("physical input produces only private aggregates and hashed provenance without certifying fit", async (t) => {
  const { input, output, directory } = await workspace(t);
  const dataset = example(), bytes = JSON.stringify(dataset, null, 2);
  await writeFile(input, bytes);
  const result = invoke(input, output);
  assert.equal(result.status, 0, result.stderr);
  assert.equal(result.stderr, "");
  const reportBytes = await readFile(output, "utf8"), report = JSON.parse(reportBytes);
  assert.deepEqual(JSON.parse(result.stdout), { status: "PRIVATE_REPORT_WRITTEN", reportSha256: hash(reportBytes), calibratedFitAvailable: false });
  assert.deepEqual(report.metrics, {
    unit: "cm", meanSignedErrorCm: 0.333333, meanAbsoluteErrorCm: 1.666667,
    rootMeanSquareErrorCm: 1.732051, maxAbsoluteErrorCm: 2, meanReferenceUncertaintyCm: 0.5,
  });
  assert.equal(report.fixtureCount, 3);
  assert.equal(report.garmentCount, 2);
  assert.equal(report.dimensionCount, 3);
  assert.deepEqual(report.physicalBenchmark, { status: "INPUTS_RECORDED_UNVERIFIED", physicalGarmentCount: 2, physicalMeasurementCount: 3 });
  assert.equal(report.calibratedFitAvailable, false);
  assert.match(report.limits, /not independently verified/);
  assert.equal(report.provenance.inputSha256, hash(bytes));
  assert.equal(report.provenance.evaluatorSha256, hash(await readFile(path.join(repository, "brandme-frontend/features/spatial/fitEvidence.ts"))));
  assert.equal(report.provenance.importerSha256, hash(await readFile(cli)));
  for (const [key, value] of Object.entries(dataset.protocol)) assert.equal(report.method[key], `sha256:${hash(value)}`);
  for (const privateValue of [directory, ...Object.values(dataset.protocol), ...dataset.points.flatMap((point) => [point.fixtureId, point.garmentRef, String(point.referenceCm), String(point.estimateCm)])]) {
    assert.ok(!reportBytes.includes(privateValue), "Report exposed a private input value");
    assert.ok(!result.stdout.includes(privateValue), "Stdout exposed a private input value");
  }
  for (const key of ["points", "fixtureId", "garmentRef", "referenceCm", "estimateCm"]) assert.ok(!Object.hasOwn(report, key));
  assert.equal(await readFile(input, "utf8"), bytes);
  if (process.platform !== "win32") assert.equal((await stat(output)).mode & 0o777, 0o600);
});

test("synthetic, malformed, duplicate, or identifying records produce no report and no input echo", async (t) => {
  const { input, output } = await workspace(t);
  const invalid = [
    { ...example(), kind: "synthetic-arithmetic" },
    { ...example(), kind: "physical-verified" },
    { ...example(), subjectName: "private-person-marker" },
    { ...example(), protocol: { referenceMethod: "private-person-marker" } },
    { ...example(), protocol: { ...example().protocol, evidenceRef: "private person with spaces" } },
    { ...example(), points: [] },
    { ...example(), points: [example().points[0], example().points[0]] },
    { ...example(), points: [example().points[0], { ...example().points[0], fixtureId: "other-fixture" }] },
    { ...example(), points: [{ ...example().points[0], referenceCm: 19 }] },
    { ...example(), points: [{ ...example().points[0], referenceUncertaintyCm: 21 }] },
    { ...example(), points: [{ ...example().points[0], bodySubject: "private-person-marker" }] },
    { ...example(), points: [{ ...example().points[0], estimateCm: "private-person-marker" }] },
  ];
  for (const value of invalid) {
    await writeFile(input, JSON.stringify(value));
    rejected(invoke(input, output), "INVALID_DATASET");
    await absent(output);
  }
  const source = JSON.stringify(example());
  for (const malformed of ["{private-person-marker", source.replace('"physical-garment"', '"physical-garment","kind":"physical-garment"'),
    source.replace('"kind":', '"k\\u0069nd":"physical-garment","kind":'), source.replace("113.237", "1e400"), Buffer.from([0xff, 0xfe])]) {
    await writeFile(input, malformed);
    rejected(invoke(input, output), "INVALID_DATASET");
    await absent(output);
  }
});

test("input byte and point bounds reject oversized data", async (t) => {
  const { input, output } = await workspace(t);
  await writeFile(input, " ".repeat(4 * 1024 * 1024 + 1));
  rejected(invoke(input, output), "INPUT_FILE");
  await absent(output);
  await writeFile(input, JSON.stringify({ ...example(), points: Array.from({ length: 10_001 }, (_, i) => ({ ...example().points[0], fixtureId: `point-${i}`, garmentRef: `garment-${i}` })) }));
  rejected(invoke(input, output), "INVALID_DATASET");
  await absent(output);
});

test("explicit paths are mandatory and existing files are never replaced", async (t) => {
  const { input, output } = await workspace(t);
  const original = JSON.stringify(example());
  await writeFile(input, original);
  for (const args of [[], ["--input", input], ["--input", input, "--input", output], ["--input", input, "--unknown", output]]) rejected(invoke(input, output, args), "ARGUMENTS");
  rejected(invoke(input, input), "ARGUMENTS");
  rejected(invoke("relative.json", output), "UNSAFE_PATH");
  await writeFile(output, "existing-private-report-marker");
  rejected(invoke(input, output), "OUTPUT_EXISTS");
  assert.equal(await readFile(output, "utf8"), "existing-private-report-marker");
  assert.equal(await readFile(input, "utf8"), original);
});

test("repository inputs, repository outputs, and missing output directories are refused", async (t) => {
  const { input, output, directory } = await workspace(t);
  await writeFile(input, JSON.stringify(example()));
  const forbidden = path.join(repository, `scripts/assets/evidence/private-intake-test-${randomUUID()}.json`);
  t.after(() => rm(forbidden, { force: true }));
  rejected(invoke(input, forbidden), "UNSAFE_PATH");
  await absent(forbidden);
  rejected(invoke(path.join(repository, "scripts/assets/evidence/fit-evidence.json"), output), "UNSAFE_PATH");
  rejected(invoke(input, path.join(directory, "missing", "report.json")), "UNSAFE_PATH");
  await absent(path.join(directory, "missing"));
  // A different repository/worktree is forbidden too; .git can be a directory or a file.
  for (const gitKind of ["directory", "file"]) {
    const nested = path.join(directory, gitKind);
    await mkdir(nested);
    if (gitKind === "directory") await mkdir(path.join(nested, ".git"));
    else await writeFile(path.join(nested, ".git"), "gitdir: private-git-worktree-marker");
    const nestedInput = path.join(nested, "input.json");
    await writeFile(nestedInput, JSON.stringify(example()));
    rejected(invoke(nestedInput, output), "UNSAFE_PATH");
    rejected(invoke(input, path.join(nested, "output.json")), "UNSAFE_PATH");
    await absent(path.join(nested, "output.json"));
  }
});

test("symbolic directory links, traversal, and hard-linked input cannot bypass path boundaries", async (t) => {
  const { input, output, directory } = await workspace(t);
  await writeFile(input, JSON.stringify(example()));
  const privateDirectory = path.join(directory, "real-private");
  await mkdir(privateDirectory);
  await writeFile(path.join(privateDirectory, "input.json"), JSON.stringify(example()));
  const directoryLink = path.join(directory, "linked-private");
  await symlink(privateDirectory, directoryLink, process.platform === "win32" ? "junction" : "dir");
  rejected(invoke(path.join(directoryLink, "input.json"), output), "UNSAFE_PATH");
  rejected(invoke(input, path.join(directoryLink, "output.json")), "UNSAFE_PATH");
  await absent(path.join(privateDirectory, "output.json"));
  const repositoryLink = path.join(directory, "linked-repository");
  await symlink(repository, repositoryLink, process.platform === "win32" ? "junction" : "dir");
  rejected(invoke(input, path.join(repositoryLink, "report.json")), "UNSAFE_PATH");
  rejected(invoke(input, `${privateDirectory}${path.sep}..${path.sep}output.json`), "UNSAFE_PATH");
  const hardlink = path.join(directory, "hardlink.json");
  await link(input, hardlink);
  rejected(invoke(hardlink, output), "INPUT_FILE");
  await absent(output);
});

test("concurrent reports never overwrite the winner", async (t) => {
  const { input, output } = await workspace(t);
  await writeFile(input, JSON.stringify(example()));
  // Exclusive creation is rechecked after evaluation, not just before reading input.
  const { spawn } = await import("node:child_process");
  const run = () => new Promise((resolve, reject) => {
    const child = spawn(process.execPath, [cli, "--input", input, "--output", output], { cwd: repository });
    let stdout = "", stderr = "";
    child.stdout.on("data", (chunk) => { stdout += chunk; });
    child.stderr.on("data", (chunk) => { stderr += chunk; });
    child.on("error", reject);
    child.on("close", (status) => resolve({ status, stdout, stderr }));
  });
  const results = await Promise.all([run(), run()]);
  assert.deepEqual(results.map((r) => r.status).sort(), [0, 1]);
  rejected(results.find((r) => r.status === 1), "OUTPUT_EXISTS");
  assert.equal(JSON.parse(results.find((r) => r.status === 0).stdout).reportSha256, hash(await readFile(output)));
});

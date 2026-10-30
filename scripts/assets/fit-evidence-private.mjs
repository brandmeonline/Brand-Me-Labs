import { constants } from "node:fs";
import { lstat, open, readFile, realpath, unlink } from "node:fs/promises";
import { createHash } from "node:crypto";
import path from "node:path";
import { fileURLToPath } from "node:url";
import ts from "typescript";

const importerPath = fileURLToPath(import.meta.url);
const repository = await realpath(path.resolve(path.dirname(importerPath), "../.."));
const evaluatorPath = path.join(repository, "brandme-frontend/features/spatial/fitEvidence.ts");
const MAX_INPUT_BYTES = 4 * 1024 * 1024;
const messages = {
  ARGUMENTS: "Use --input and --output with distinct absolute JSON file paths; see --help.",
  UNSAFE_PATH: "Use local JSON file paths outside all Git worktrees, without parent traversal or symbolic links, in existing directories.",
  INPUT_FILE: "Input must be a readable regular file with one hard link and at most 4 MiB.",
  INPUT_CHANGED: "Input changed during intake. Stop other writers and retry with a stable file.",
  INVALID_DATASET: "Input must match the physical-garment evidence schema, with unique points and complete opaque protocol references.",
  OUTPUT_EXISTS: "Output already exists. Choose a new private report filename; nothing was overwritten.",
  OUTPUT_FAILED: "The private report could not be written. Check the chosen directory and inspect it before retrying.",
  INTAKE_FAILED: "Intake could not complete. No input values or paths are logged.",
};
class IntakeError extends Error {
  constructor(code) { super(messages[code]); this.code = code; }
}
const fail = (code) => { throw new IntakeError(code); };
const sha256 = (value) => createHash("sha256").update(value).digest("hex");
const sameFile = (a, b) => a.dev === b.dev && a.ino === b.ino;
const comparable = (value) => process.platform === "win32" ? value.toLowerCase() : value;
function inside(directory, file) {
  const relative = path.relative(comparable(directory), comparable(file));
  return relative === "" || (!relative.startsWith(`..${path.sep}`) && relative !== ".." && !path.isAbsolute(relative));
}

function absoluteJsonPath(value) {
  if (typeof value !== "string" || !path.isAbsolute(value) || /[\u0000-\u001f\u007f]/u.test(value) ||
      value.split(/[\\/]/u).includes("..") || path.extname(value).toLowerCase() !== ".json") fail("UNSAFE_PATH");
  if (process.platform === "win32") {
    // Reject UNC/device namespaces, alternate data streams, and Windows filename aliases.
    if (!/^[a-z]:[\\/]/i.test(value) || value.slice(2).includes(":")) fail("UNSAFE_PATH");
    for (const part of value.slice(3).split(/[\\/]/u)) {
      if (/[. ]$/.test(part) || /^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)/i.test(part)) fail("UNSAFE_PATH");
    }
  }
  const file = path.resolve(value);
  if (inside(repository, file)) fail("UNSAFE_PATH");
  return file;
}

async function statOrMissing(file) {
  try { return await lstat(file); }
  catch (error) { if (error.code === "ENOENT") return null; throw error; }
}

async function checkedParent(file) {
  const parent = path.dirname(file);
  const parsed = path.parse(parent);
  let current = parsed.root;
  const directories = [current];
  for (const part of parent.slice(parsed.root.length).split(path.sep).filter(Boolean)) {
    current = path.join(current, part);
    directories.push(current);
  }
  for (const directory of directories) {
    const info = await statOrMissing(directory);
    if (!info?.isDirectory() || info.isSymbolicLink() || await statOrMissing(path.join(directory, ".git"))) fail("UNSAFE_PATH");
  }
  const canonical = await realpath(parent);
  if (inside(repository, canonical) || comparable(canonical) !== comparable(parent)) fail("UNSAFE_PATH");
  return await lstat(parent);
}

async function readPrivateInput(file) {
  await checkedParent(file);
  const before = await statOrMissing(file);
  if (!before?.isFile() || before.isSymbolicLink() || before.nlink !== 1 || before.size > MAX_INPUT_BYTES) fail("INPUT_FILE");
  const handle = await open(file, constants.O_RDONLY | (constants.O_NOFOLLOW ?? 0));
  try {
    const opened = await handle.stat();
    if (!sameFile(before, opened) || !opened.isFile() || opened.nlink !== 1) fail("INPUT_CHANGED");
    // Bounded reads also cover an input that grows after the initial size check.
    const bytes = Buffer.alloc(MAX_INPUT_BYTES + 1);
    let length = 0;
    while (length < bytes.length) {
      const { bytesRead } = await handle.read(bytes, length, bytes.length - length, null);
      if (!bytesRead) break;
      length += bytesRead;
    }
    if (length > MAX_INPUT_BYTES) fail("INPUT_FILE");
    const after = await handle.stat();
    const named = await lstat(file);
    await checkedParent(file);
    if (!sameFile(opened, named) || named.isSymbolicLink() || after.nlink !== 1 ||
        after.size !== opened.size || after.mtimeMs !== opened.mtimeMs || after.ctimeMs !== opened.ctimeMs || length !== after.size) fail("INPUT_CHANGED");
    return bytes.subarray(0, length);
  } finally { await handle.close(); }
}

function parseJson(bytes) {
  try {
    const text = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
    const value = JSON.parse(text);
    // JSON.parse accepts repeated object keys. Reject them before the schema validator
    // can see only the last value. Syntax is already checked; this walker only scans keys.
    let offset = 0;
    const space = () => { while (/\s/.test(text[offset] ?? "") && offset < text.length) offset++; };
    function string() {
      const start = offset++;
      while (text[offset] !== '"') { if (text[offset] === "\\") offset++; offset++; }
      return JSON.parse(text.slice(start, ++offset));
    }
    function walk(depth = 0) {
      if (depth > 8) fail("INVALID_DATASET");
      space();
      if (text[offset] === '"') { string(); return; }
      const kind = text[offset];
      if (kind !== "{" && kind !== "[") {
        while (offset < text.length && !/[\s,}\]]/.test(text[offset])) offset++;
        return;
      }
      offset++;
      const close = kind === "{" ? "}" : "]", keys = new Set();
      space();
      while (text[offset] !== close) {
        if (kind === "{") {
          const key = string();
          if (keys.has(key)) fail("INVALID_DATASET");
          keys.add(key); space(); offset++; // colon
        }
        walk(depth + 1); space();
        if (text[offset] === ",") { offset++; space(); }
      }
      offset++;
    }
    walk();
    return value;
  } catch { fail("INVALID_DATASET"); }
}

async function aggregateReport(bytes) {
  const source = await readFile(evaluatorPath, "utf8");
  const { outputText } = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ES2022 } });
  const { evaluateGarmentEvidence } = await import(`data:text/javascript;base64,${Buffer.from(outputText).toString("base64")}`);
  let result;
  try {
    result = evaluateGarmentEvidence(parseJson(bytes));
    if (result.kind !== "physical-garment") fail("INVALID_DATASET");
  } catch { fail("INVALID_DATASET"); }
  const opaque = (value) => `sha256:${sha256(value)}`;
  // Explicit projection: no points, garment IDs, paths, or caller-supplied labels.
  return {
    reportSchemaVersion: "private-garment-evidence-report-v1",
    schemaVersion: result.schemaVersion,
    kind: result.kind,
    method: {
      referenceMethod: opaque(result.method.referenceMethod),
      estimateMethod: opaque(result.method.estimateMethod),
      revision: opaque(result.method.revision),
      evidenceRef: opaque(result.method.evidenceRef),
      referenceEncoding: "sha256 of the exact UTF-8 protocol value; resolve against the private input and method record",
      scope: "Supplied garment chest/waist/hip circumference comparisons only; no body-reading intake or estimation engine.",
      errorDefinition: result.method.errorDefinition,
      aggregation: result.method.aggregation,
      referenceUncertainty: result.method.referenceUncertainty,
    },
    fixtureCount: result.fixtureCount,
    garmentCount: result.garmentCount,
    dimensionCount: result.dimensionCount,
    metrics: {
      unit: result.metrics.unit,
      meanSignedErrorCm: result.metrics.meanSignedErrorCm,
      meanAbsoluteErrorCm: result.metrics.meanAbsoluteErrorCm,
      rootMeanSquareErrorCm: result.metrics.rootMeanSquareErrorCm,
      maxAbsoluteErrorCm: result.metrics.maxAbsoluteErrorCm,
      meanReferenceUncertaintyCm: result.metrics.meanReferenceUncertaintyCm,
    },
    physicalBenchmark: {
      status: result.physicalBenchmark.status,
      physicalGarmentCount: result.physicalBenchmark.physicalGarmentCount,
      physicalMeasurementCount: result.physicalBenchmark.physicalMeasurementCount,
    },
    calibratedFitAvailable: false,
    limits: result.limits,
    provenance: {
      algorithm: "sha256",
      inputSha256: sha256(bytes),
      evaluatorSha256: sha256(source),
      importerSha256: sha256(await readFile(importerPath)),
      verification: "Input labels and measurements are supplied by the operator; hashes establish byte identity, not truth or independent verification.",
    },
  };
}

async function writePrivateReport(file, report) {
  const parent = await checkedParent(file);
  if (await statOrMissing(file)) fail("OUTPUT_EXISTS");
  let handle, created;
  try {
    handle = await open(file, constants.O_WRONLY | constants.O_CREAT | constants.O_EXCL | (constants.O_NOFOLLOW ?? 0), 0o600);
    created = await handle.stat();
    const checked = await checkedParent(file), named = await lstat(file);
    if (!sameFile(parent, checked) || !sameFile(created, named) || named.isSymbolicLink() || created.nlink !== 1) fail("UNSAFE_PATH");
    const text = `${JSON.stringify(report, null, 2)}\n`;
    await handle.writeFile(text, "utf8");
    await handle.sync();
    return sha256(text);
  } catch (error) {
    // Remove only our own incomplete file, and only while its safe path and inode agree.
    if (created) {
      try {
        await checkedParent(file);
        const named = await lstat(file);
        if (!named.isSymbolicLink() && sameFile(created, named)) {
          await handle.close(); handle = null;
          await unlink(file);
        }
      } catch { /* Never follow a moved/symlinked path for cleanup. */ }
    }
    if (error instanceof IntakeError) throw error;
    fail(error.code === "EEXIST" ? "OUTPUT_EXISTS" : "OUTPUT_FAILED");
  } finally { await handle?.close(); }
}

async function main() {
  const args = process.argv.slice(2);
  if (args.length === 1 && args[0] === "--help") {
    console.log("Usage: node scripts/assets/fit-evidence-private.mjs --input <absolute-private.json> --output <new-absolute-private-report.json>\nBoth paths must be outside Git worktrees, without symlinks, in existing directories. Input: physical-garment schema only, UTF-8, <=4 MiB. Output: private aggregate metrics and hashed references; never independently verified or calibrated fit. See scripts/assets/FIT-EVIDENCE-PRIVATE.md.");
    return;
  }
  if (args.length !== 4 || !["--input", "--output"].includes(args[0]) || !["--input", "--output"].includes(args[2]) || args[0] === args[2]) fail("ARGUMENTS");
  const values = new Map([[args[0], args[1]], [args[2], args[3]]]);
  const input = absoluteJsonPath(values.get("--input")), output = absoluteJsonPath(values.get("--output"));
  if (comparable(input) === comparable(output)) fail("ARGUMENTS");
  await checkedParent(output);
  if (await statOrMissing(output)) fail("OUTPUT_EXISTS");
  const report = await aggregateReport(await readPrivateInput(input));
  const reportSha256 = await writePrivateReport(output, report);
  console.log(JSON.stringify({ status: "PRIVATE_REPORT_WRITTEN", reportSha256, calibratedFitAvailable: false }));
}

try { await main(); }
catch (error) {
  const code = error instanceof IntakeError ? error.code : "INTAKE_FAILED";
  console.error(JSON.stringify({ status: "REJECTED", code, message: messages[code] }));
  process.exitCode = 1;
}

import { readFile, mkdir, writeFile } from "node:fs/promises";
import { createHash } from "node:crypto";
import path from "node:path";
import { fileURLToPath } from "node:url";
import ts from "typescript";

// Run the same pure TypeScript evaluator used by application tests on Node 20+.
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const source = await readFile(path.join(root, "brandme-frontend/features/spatial/fitEvidence.ts"), "utf8");
const { outputText } = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ES2022 } });
const { evaluateGarmentEvidence } = await import(`data:text/javascript;base64,${Buffer.from(outputText).toString("base64")}`);

// Entirely invented reference dimensions + deliberate errors exercise the arithmetic.
// Never substitute these fixtures for a real garment/operator/model measurement session.
const fixture = {
  schemaVersion: "garment-dimension-evidence-v1",
  kind: "synthetic-arithmetic",
  protocol: {
    referenceMethod: "invented-reference-circumferences-v1",
    estimateMethod: "reference-plus-known-offset-v1",
    revision: "synthetic-v1",
    evidenceRef: "synthetic-arithmetic-fixtures-v1",
  },
  points: [
    { fixtureId: "synthetic-shirt-chest", garmentRef: "synthetic-shirt", dimension: "chest", referenceCm: 108, referenceUncertaintyCm: 0, estimateCm: 109 },
    { fixtureId: "synthetic-shirt-waist", garmentRef: "synthetic-shirt", dimension: "waist", referenceCm: 104, referenceUncertaintyCm: 0, estimateCm: 102 },
    { fixtureId: "synthetic-trouser-waist", garmentRef: "synthetic-trouser", dimension: "waist", referenceCm: 88, referenceUncertaintyCm: 0, estimateCm: 88.5 },
    { fixtureId: "synthetic-trouser-hip", garmentRef: "synthetic-trouser", dimension: "hip", referenceCm: 108, referenceUncertaintyCm: 0, estimateCm: 107.5 },
    { fixtureId: "synthetic-dress-chest", garmentRef: "synthetic-dress", dimension: "chest", referenceCm: 96, referenceUncertaintyCm: 0, estimateCm: 96 },
    { fixtureId: "synthetic-dress-hip", garmentRef: "synthetic-dress", dimension: "hip", referenceCm: 104, referenceUncertaintyCm: 0, estimateCm: 105 },
  ],
};
if (process.argv.length > 2) throw Error("This command only runs repository-owned synthetic fixtures; it does not ingest body or physical-session data.");
const report = {
  ...evaluateGarmentEvidence(fixture),
  fixtureSha256: createHash("sha256").update(JSON.stringify(fixture)).digest("hex"),
  evaluatorSha256: createHash("sha256").update(source).digest("hex"),
  reproduction: "node scripts/assets/fit-evidence.mjs",
};
const outDir = path.join(root, "scripts/assets/evidence");
await mkdir(outDir, { recursive: true });
await writeFile(path.join(outDir, "fit-evidence.json"), `${JSON.stringify(report, null, 2)}\n`);
console.log(JSON.stringify(report, null, 2));

import { readFile, readdir, stat } from "node:fs/promises";
import { createHash } from "node:crypto";
import { gunzipSync } from "node:zlib";
import { fileURLToPath } from "node:url";
import path from "node:path";
import validator from "gltf-validator";
const root = path.resolve(
    path.dirname(fileURLToPath(import.meta.url)),
    "../..",
  ),
  pub = path.join(root, "brandme-frontend/public");
const demo = JSON.parse(
    await readFile(
      path.join(root, "docs/design/brandme/contracts/demo-scenario.json"),
    ),
  ),
  failures = [];
const assert = (ok, message) => {
  if (!ok) failures.push(message);
};
const sha = (b) => createHash("sha256").update(b).digest("hex");
const local = (url) => {
  assert(
    typeof url === "string" && url.startsWith("/demo/") && !url.includes(".."),
    `Unsafe asset path ${url}`,
  );
  return path.join(pub, url);
};
const required = [
  ...demo.rooms.flatMap((r) => [r.required_glb, r.required_poster]),
  ...demo.products.flatMap((p) => Object.values(p.required_assets)),
];
for (const f of required) {
  try {
    assert((await stat(local(f))).size > 0, `Empty ${f}`);
  } catch {
    failures.push(`Missing required file ${f}`);
  }
}
let manifests = [];
async function walk(dir) {
  for (const item of await readdir(dir, { withFileTypes: true })) {
    const p = path.join(dir, item.name);
    if (item.isDirectory()) await walk(p);
    else if (item.name === "manifest.json") manifests.push(p);
  }
}
await walk(path.join(pub, "demo"));
const report = [];
for (const file of manifests) {
  const m = JSON.parse(await readFile(file)),
    dir = path.dirname(file);
  let triangles = 0;
  const rights = JSON.parse(await readFile(local(m.rights)));
  assert(
    rights.source && rights.author && rights.license && rights.rightsHolder,
    `${m.id}: missing rights provenance`,
  );
  assert(
    ["P0", "P1", "P2", "P3", "P4"].includes(m.fidelity) || !!m.camera,
    `${m.id}: missing fidelity`,
  );
  if (m.fidelity)
    assert(
      m.fidelity === "P0" || m.fidelity === "P1",
      `${m.id}: procedural fixture cannot claim product-specific/rigged/calibrated fidelity`,
    );
  for (const [name, metadata] of Object.entries(m.files)) {
    assert(
      !name.includes("/") && !name.includes(".."),
      `${m.id}: unsafe filename`,
    );
    const b = await readFile(path.join(dir, name));
    assert(
      metadata.sha256 === sha(b) && metadata.bytes === b.length,
      `${m.id}/${name}: hash or size mismatch`,
    );
    if (name.endsWith(".webp"))
      assert(
        b.toString("ascii", 0, 4) === "RIFF" &&
          b.toString("ascii", 8, 12) === "WEBP",
        `${m.id}: invalid WebP`,
      );
    if (name.endsWith(".gz")) {
      const original = await readFile(path.join(dir, name.slice(0, -3)));
      assert(gunzipSync(b).equals(original), `${m.id}: compression mismatch`);
    }
    if (name.endsWith(".usdz")) {
      assert(b.readUInt32LE(0) === 0x04034b50, `${m.id}: invalid USDZ zip`);
      let offset = 0,
        entries = 0;
      while (offset + 30 < b.length && b.readUInt32LE(offset) === 0x04034b50) {
        const method = b.readUInt16LE(offset + 8),
          length = b.readUInt32LE(offset + 18),
          n = b.readUInt16LE(offset + 26),
          e = b.readUInt16LE(offset + 28),
          start = offset + 30 + n + e,
          name = b.toString("utf8", offset + 30, offset + 30 + n);
        assert(
          method === 0 && start % 64 === 0,
          `${m.id}: USDZ must be uncompressed and 64-byte aligned`,
        );
        assert(
          !name.includes("..") && !name.startsWith("/"),
          `${m.id}: unsafe USDZ member`,
        );
        offset = start + length;
        entries++;
      }
      assert(entries > 1, `${m.id}: missing USD scene/geometry entries`);
    }
    if (!name.endsWith(".glb")) continue;
    assert(b.length < 16 * 1024 * 1024, `${m.id}: oversized GLB`);
    assert(
      b.toString("ascii", 0, 4) === "glTF" &&
        b.readUInt32LE(4) === 2 &&
        b.readUInt32LE(8) === b.length,
      `${m.id}: bad GLB header`,
    );
    const result = await validator.validateBytes(new Uint8Array(b), {
      maxIssues: 30,
    });
    assert(
      result.issues.numErrors === 0,
      `${m.id}/${name}: glTF errors ${JSON.stringify(result.issues.messages.filter((x) => x.severity === 0))}`,
    );
    const j = JSON.parse(b.subarray(20, 20 + b.readUInt32LE(12)).toString());
    assert(
      !(j.buffers || []).some((x) => x.uri) &&
        !(j.images || []).some((x) => x.uri),
      `${m.id}: external/data references forbidden`,
    );
    assert(
      j.meshes.length <= 16 && j.images?.length <= 36,
      `${m.id}: excessive meshes/textures`,
    );
    for (const node of j.nodes)
      for (const key of ["matrix", "translation", "rotation", "scale"])
        if (node[key])
          assert(
            node[key].every(Number.isFinite),
            `${m.id}: nonfinite transform`,
          );
    const count = j.meshes.reduce(
      (sum, mesh) =>
        sum +
        mesh.primitives.reduce(
          (s, p) =>
            s + j.accessors[p.indices ?? p.attributes.POSITION].count / 3,
          0,
        ),
      0,
    );
    if (name === "lod1.glb")
      assert(
        b.length <= 750 * 1024 && count <= 12000,
        `${m.id}: low LOD exceeds 750KB/12k triangles`,
      );
    if (name === "lod0.glb")
      assert(
        b.length <= 2 * 1024 * 1024,
        `${m.id}: inspection model exceeds 2MB`,
      );
    triangles = Math.max(triangles, count);
  }
  if (m.dimensionsMeters) {
    assert(
      m.dimensionsMeters.every((v) => Number.isFinite(v) && v > 0 && v < 8),
      `${m.id}: dimensions invalid`,
    );
    assert(
      m.collisionBounds?.min?.every(Number.isFinite) &&
        m.collisionBounds?.max?.every(Number.isFinite),
      `${m.id}: bounds invalid`,
    );
  }
  if (!m.camera && m.fidelity !== "P0")
    assert(
      m.pivot &&
        m.displayScaleBounds?.[0] > 0 &&
        m.displayScaleBounds?.[1] <= 2,
      `${m.id}: pivot/scale bounds missing`,
    );
  report.push({ id: m.id, triangles, files: Object.keys(m.files).length });
}
const catalog = JSON.parse(await readFile(path.join(pub, "demo/catalog.json")));
for (const r of catalog.rooms) {
  const garmentWorst = Math.max(
    ...catalog.products.map((x) => x.files["lod1.glb.gz"].bytes),
  );
  assert(
    r.files["room.glb.gz"].bytes + 12 * garmentWorst < 4 * 1024 * 1024,
    `${r.id}: first-use entry payload >4MB`,
  );
  assert(
    r.drawCalls + 12 * Math.max(...catalog.products.map((x) => x.drawCalls)) <
      100,
    `${r.id}: estimated entry draw calls >100`,
  );
}
assert(
  (await readFile(path.join(pub, "demo/catalog.json"))).equals(
    await readFile(
      path.join(
        root,
        "brandme-frontend/features/spatial/generated-catalog.json",
      ),
    ),
  ),
  "Generated component catalog differs from validated asset catalog",
);
if (failures.length) {
  console.error(failures.join("\n"));
  process.exitCode = 1;
} else
  console.log(
    JSON.stringify(
      {
        status: "passed",
        requiredPaths: required.length,
        manifests: manifests.length,
        assets: report,
        limitations:
          "Structural validation and estimated budgets only; native device handoffs/field performance require separate evidence.",
      },
      null,
      2,
    ),
  );

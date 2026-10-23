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
const supplementary = [];
const png = (b, label) => {
  assert(
    b.length >= 24 && b.subarray(0, 8).toString("hex") === "89504e470d0a1a0a",
    `${label}: invalid PNG`,
  );
  if (b.length >= 24)
    assert(
      b.readUInt32BE(16) > 0 &&
        b.readUInt32BE(20) > 0 &&
        b.readUInt32BE(16) * b.readUInt32BE(20) <= 16000000,
      `${label}: invalid PNG dimensions`,
    );
};
for (const file of manifests) {
  const m = JSON.parse(await readFile(file)),
    dir = path.dirname(file);
  if (dir === path.join(pub, "demo/vision")) {
    assert(
      m.schemaVersion === 1 &&
        m.developmentOnly === true &&
        m.runtime === "0.10.35" &&
        m.modelUrl === "/demo/vision/pose-lite-v1.task" &&
        m.wasmRoot === "/demo/vision/0.10.35/wasm",
      "Vision: wrong development model/runtime pin",
    );
    const expected = [
      "0.10.35/vision_bundle.js",
      "0.10.35/wasm/vision_wasm_internal.js",
      "0.10.35/wasm/vision_wasm_internal.wasm",
      "0.10.35/wasm/vision_wasm_nosimd_internal.js",
      "0.10.35/wasm/vision_wasm_nosimd_internal.wasm",
      "pose-lite-v1.task",
    ];
    assert(
      JSON.stringify(Object.keys(m.files).sort()) ===
        JSON.stringify(expected.sort()),
      "Vision: unexpected payload files",
    );
    for (const name of expected) {
      const b = await readFile(path.join(dir, name));
      assert(
        m.files[name]?.sha256 === sha(b) && m.files[name]?.bytes === b.length,
        `Vision ${name}: hash/size mismatch`,
      );
      if (name.endsWith(".task"))
        assert(
          sha(b) ===
            "59929e1d1ee95287735ddd833b19cf4ac46d29bc7afddbbf6753c459690d574a",
          "Vision: model does not match pinned source",
        );
    }
    supplementary.push({
      id: "local-dev-vision",
      files: expected.length,
      redistributed: false,
    });
    continue;
  }
  if (dir === path.join(pub, "demo/overlays")) {
    assert(
      m.fidelity === "P1" &&
        m.fit === false &&
        m.bodyBinding === false &&
        m.rights === "/demo/rights.json" &&
        !!m.source,
      "Overlays: provenance/fidelity missing",
    );
    assert(
      JSON.stringify(m.assets.map((a) => a.slug).sort()) ===
        JSON.stringify(["jacket", "knit", "overshirt", "tee"]),
      "Overlays: wrong supported garment set",
    );
    for (const a of m.assets) {
      assert(
        a.file === `/demo/overlays/${a.slug}.png`,
        "Overlay: unexpected path",
      );
      const b = await readFile(local(a.file));
      assert(
        a.sha256 === sha(b) && a.bytes === b.length,
        `${a.slug} overlay: hash/size mismatch`,
      );
      assert(
        a.dimensions?.length === 3 &&
          a.dimensions.every((v) => Number.isFinite(v) && v > 0) &&
          a.removed.includes("aged_brass") &&
          a.removed.includes("ash_grain"),
        `${a.slug} overlay: export metadata missing`,
      );
      png(b, a.slug);
    }
    supplementary.push({
      id: "original-overlays",
      files: m.assets.length,
      fidelity: "P1",
    });
    continue;
  }
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
    if (name === "lod1.glb" || name === "folded.glb")
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
  if (m.folded) {
    const f = m.folded;
    assert(
      f.fidelity === "P1" && f.rights === m.rights && !!f.source,
      `${m.id}: folded variant needs approximate fidelity and provenance`,
    );
    assert(
      f.pivot === "grounded_bottom_center" &&
        Math.abs(f.collisionBounds?.min?.[1]) < 0.0001 &&
        f.dimensionsMeters?.every(
          (v) => Number.isFinite(v) && v > 0 && v < 0.5,
        ),
      `${m.id}: folded variant needs grounded bounds and plausible dimensions`,
    );
    for (const url of [f.glb, f.poster])
      assert(
        path.dirname(url) === path.dirname(m.glb) &&
          !!m.files[path.basename(url)],
        `${m.id}: folded preview must be included in the hash-checked manifest`,
      );
    assert(
      f.triangleCount <= 12000 && f.drawCalls <= 3,
      `${m.id}: folded variant exceeds its 12k triangle / 3 draw budget`,
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
const fixtureDir = path.join(pub, "demo/test-person");
const fixtureRights = JSON.parse(
  await readFile(path.join(fixtureDir, "rights.json")),
);
const fixture = await readFile(path.join(fixtureDir, "synthetic-adult.png"));
const annotation = JSON.parse(
  await readFile(path.join(fixtureDir, "annotations.json")),
);
assert(
  fixtureRights.file === "synthetic-adult.png" &&
    !!fixtureRights.creator &&
    !!fixtureRights.rights &&
    !!fixtureRights.use &&
    !!fixtureRights.prompt &&
    fixtureRights.sha256 === sha(fixture) &&
    fixtureRights.bytes === fixture.length,
  "Synthetic fixture: provenance/hash/size missing",
);
png(fixture, "Synthetic fixture");
assert(
  annotation.width === fixture.readUInt32BE(16) &&
    annotation.height === fixture.readUInt32BE(20) &&
    annotation.annotationUncertaintyPixels > 0 &&
    annotation.method.includes("not surveyed") &&
    Object.keys(annotation.points).length === 8 &&
    Object.values(annotation.points).every(
      (p) =>
        p.length === 2 &&
        p.every((v) => Number.isFinite(v) && v >= 0 && v <= 1),
    ),
  "Synthetic fixture: invalid coarse annotation",
);
supplementary.push({
  id: "synthetic-adult",
  files: 1,
  physicalGroundTruth: false,
});
const catalog = JSON.parse(await readFile(path.join(pub, "demo/catalog.json")));
for (const r of catalog.rooms) {
  const shelf = r.groups.find((g) => g.id === "shelf.folded");
  assert(
    shelf?.positions?.length === shelf?.capacity &&
      shelf.positions.every((p) => p.length === 3 && p.every(Number.isFinite)),
    `${r.id}: folded shelf needs six explicit grounded destinations`,
  );
  const variants = catalog.products
    .filter((p) => p.folded)
    .map((p) => p.folded);
  const widest = Math.max(...variants.map((f) => f.dimensionsMeters[0]));
  const tallest = Math.max(...variants.map((f) => f.dimensionsMeters[1]));
  for (let i = 0; i < (shelf?.positions?.length ?? 0); i++)
    for (let j = i + 1; j < shelf.positions.length; j++) {
      const a = shelf.positions[i],
        b = shelf.positions[j];
      assert(
        Math.abs(a[0] - b[0]) > widest || Math.abs(a[1] - b[1]) > tallest,
        `${r.id}: folded destinations ${i}/${j} overlap`,
      );
    }
  const garmentWorst = Math.max(
    ...catalog.products.flatMap((x) => [
      x.files["lod1.glb.gz"].bytes,
      x.files["folded.glb.gz"]?.bytes ?? 0,
    ]),
  );
  assert(
    r.files["room.glb.gz"].bytes + 12 * garmentWorst < 4 * 1024 * 1024,
    `${r.id}: first-use entry payload >4MB`,
  );
  assert(
    r.drawCalls +
      12 *
        Math.max(
          ...catalog.products.flatMap((x) => [
            x.drawCalls,
            x.folded?.drawCalls ?? 0,
          ]),
        ) <
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
        manifests: report.length,
        assets: report,
        supplementary,
        limitations:
          "Structural validation and estimated budgets only; native device handoffs/field performance require separate evidence.",
      },
      null,
      2,
    ),
  );

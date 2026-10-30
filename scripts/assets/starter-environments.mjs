import * as T from "three";
import { GLTFExporter } from "three/addons/exporters/GLTFExporter.js";
import { mergeGeometries } from "three/addons/utils/BufferGeometryUtils.js";
import { RoundedBoxGeometry } from "three/addons/geometries/RoundedBoxGeometry.js";
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { createHash } from "node:crypto";
import { gzipSync, deflateSync } from "node:zlib";
import { createServer } from "node:http";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { chromium } from "@playwright/test";

const toolsDir = path.dirname(fileURLToPath(import.meta.url));
const publicRoot = path.resolve(toolsDir, "../../brandme-frontend/public");
const checkOnly = process.argv.slice(2).includes("--check");
if (process.argv.slice(2).some((argument) => argument !== "--check")) throw Error("Supported option: --check (render committed assets without changing files).");
const sha = (bytes) => createHash("sha256").update(bytes).digest("hex");
globalThis.FileReader = class {
  readAsArrayBuffer(blob) { blob.arrayBuffer().then((result) => { this.result = result; this.onloadend?.(); }); }
};
const material = (name, color, roughness = 0.82, metalness = 0) => new T.MeshStandardMaterial({ name, color, roughness, metalness });
const m = {
  wood: material("original_oak_grain", "#AD8055"), pale: material("original_birch_grain", "#CBB99C"),
  wall: material("warm_plaster", "#E2DED2"), white: material("powder_coat", "#E3E3DB"),
  metal: material("graphite_steel", "#303D3B", 0.4, 0.6), brass: material("warm_rail", "#978063", 0.35, 0.65),
  rust: material("rust_woven", "#A16F55"), sage: material("sage_woven", "#839489"), linen: material("ivory_woven", "#C9C1B0"),
};
function box(group, size, position, mat, radius = 0.005) {
  const mesh = new T.Mesh(new RoundedBoxGeometry(...size, 1, radius), mat);
  mesh.position.set(...position); group.add(mesh); return mesh;
}
function rod(group, from, to, mat, radius = 0.012) {
  const a = new T.Vector3(...from), b = new T.Vector3(...to);
  const mesh = new T.Mesh(new T.CylinderGeometry(radius, radius, a.distanceTo(b), 12), mat);
  mesh.position.copy(a.add(b).multiplyScalar(0.5));
  mesh.quaternion.setFromUnitVectors(new T.Vector3(0, 1, 0), new T.Vector3(...to).sub(new T.Vector3(...from)).normalize());
  group.add(mesh);
}
function room(modular) {
  const group = new T.Group();
  group.name = modular ? "starter_modular" : "starter_wooden";
  const timber = modular ? m.white : m.wood;
  const floor = modular ? m.pale : m.wood;
  box(group, [3.8, 0.08, 2.8], [0, -0.04, 0], floor);
  // Authored floor seams add depth without texture downloads.
  for (let x = -1.65; x <= 1.8; x += 0.3) box(group, [0.006, 0.002, 2.8], [x, 0.002, 0], m.pale, 0);
  box(group, [3.8, 2.6, 0.08], [0, 1.3, -1.4], m.wall);
  box(group, [0.08, 2.6, 2.8], [-1.9, 1.3, 0], m.wall);
  box(group, [0.08, 2.6, 2.8], [1.9, 1.3, 0], m.wall);
  box(group, [3.72, 0.07, 0.035], [0, 0.035, -1.34], timber);
  // A compact wardrobe and a six-destination shelf bank share semantic anchors.
  for (const x of [-1.72, -0.12]) box(group, [0.045, 2.24, 0.66], [x, 1.2, -0.97], timber);
  box(group, [1.65, 0.045, 0.66], [-0.92, 2.32, -0.97], timber);
  box(group, [1.65, 0.045, 0.66], [-0.92, 0.19, -0.97], timber);
  if (!modular) box(group, [1.58, 2.1, 0.025], [-0.92, 1.25, -1.27], m.pale);
  rod(group, [-1.65, 1.85, -0.86], [-0.19, 1.85, -0.86], modular ? m.metal : m.brass);
  for (const x of [0.15, 1.72]) box(group, [0.04, 2.24, 0.58], [x, 1.2, -1.0], timber);
  for (const y of [0.23, 1.03, 1.53, 2.3]) box(group, [1.61, 0.04, 0.58], [0.935, y, -1.0], timber);
  if (modular) {
    for (const x of [0.67, 1.2]) box(group, [0.028, 0.75, 0.58], [x, 0.635, -1.0], m.white);
    for (const x of [-1.69, 1.69]) rod(group, [x, 0.05, -0.77], [x, 2.35, -0.77], m.metal, 0.01);
  }
  // A small padded bench, inset rug and personal accessory tray.
  for (const x of [-1.28, -0.42]) for (const z of [0.13, 0.5]) box(group, [0.045, 0.4, 0.045], [x, 0.2, z], modular ? m.metal : timber);
  box(group, [1.05, 0.09, 0.55], [-0.85, 0.445, 0.315], modular ? m.sage : m.rust, 0.035);
  box(group, [1.8, 0.009, 1.25], [0.1, 0.006, 0.1], m.linen, 0.015);
  box(group, [0.48, 0.025, 0.3], [-0.85, 0.5025, 0.315], modular ? m.sage : m.rust);
  // Upper storage baskets are original modeled geometry, not third-party logos.
  for (const x of [0.44, 1.05]) {
    box(group, [0.46, 0.24, 0.38], [x, 2.44, -1.0], m.linen, 0.018);
    box(group, [0.1, 0.028, 0.008], [x, 2.46, -0.805], modular ? m.metal : timber);
  }
  return group;
}
function merge(group) {
  group.updateMatrixWorld(true);
  const buckets = new Map();
  group.traverse((node) => {
    if (!node.isMesh) return;
    let geometry = node.geometry.clone();
    if (geometry.index) geometry = geometry.toNonIndexed();
    geometry.applyMatrix4(node.matrixWorld);
    if (!buckets.has(node.material)) buckets.set(node.material, []);
    buckets.get(node.material).push(geometry);
  });
  const merged = new T.Group(); merged.name = group.name;
  for (const [mat, geometries] of buckets) { const mesh = new T.Mesh(mergeGeometries(geometries), mat); mesh.name = mat.name; merged.add(mesh); }
  return merged;
}
// Original, deterministic 32px grain map; GLB remains entirely self-contained.
function grainPng() {
  const crc = (bytes) => { let c = ~0; for (const byte of bytes) { c ^= byte; for (let i = 0; i < 8; i++) c = (c >>> 1) ^ (c & 1 ? 0xedb88320 : 0); } return (c ^ ~0) >>> 0; };
  const chunk = (type, bytes) => { const t = Buffer.from(type), length = Buffer.alloc(4), checksum = Buffer.alloc(4); length.writeUInt32BE(bytes.length); checksum.writeUInt32BE(crc(Buffer.concat([t, bytes]))); return Buffer.concat([length, t, bytes, checksum]); };
  const head = Buffer.alloc(13); head.writeUInt32BE(32); head.writeUInt32BE(32, 4); head[8] = 8; head[9] = 2;
  const rows = Buffer.alloc(32 * 97);
  for (let y = 0; y < 32; y++) for (let x = 0; x < 32; x++) {
    const value = 239 + Math.round(12 * Math.sin(x * 0.7 + Math.sin(y * 0.11)));
    rows.fill(value, y * 97 + 1 + x * 3, y * 97 + 4 + x * 3);
  }
  return Buffer.concat([Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]), chunk("IHDR", head), chunk("IDAT", deflateSync(rows)), chunk("IEND", Buffer.alloc(0))]);
}
function embedGrain(glb) {
  const n = glb.readUInt32LE(12), data = JSON.parse(glb.subarray(20, 20 + n));
  let binary = glb.subarray(28 + n);
  const png = grainPng(), view = data.bufferViews.length;
  data.bufferViews.push({ buffer: 0, byteOffset: binary.length, byteLength: png.length });
  binary = Buffer.concat([binary, png]); binary = Buffer.concat([binary, Buffer.alloc((4 - binary.length % 4) % 4)]);
  data.images = [{ bufferView: view, mimeType: "image/png" }]; data.samplers = [{ magFilter: 9729, minFilter: 9987, wrapS: 10497, wrapT: 10497 }]; data.textures = [{ sampler: 0, source: 0 }];
  for (const mat of data.materials) if (mat.name.includes("grain")) mat.pbrMetallicRoughness.baseColorTexture = { index: 0 };
  data.buffers[0].byteLength = binary.length;
  let json = Buffer.from(JSON.stringify(data)); json = Buffer.concat([json, Buffer.alloc((4 - json.length % 4) % 4, 32)]);
  const header = Buffer.alloc(20), binHead = Buffer.alloc(8);
  header.write("glTF"); header.writeUInt32LE(2, 4); header.writeUInt32LE(28 + json.length + binary.length, 8); header.writeUInt32LE(json.length, 12); header.write("JSON", 16);
  binHead.writeUInt32LE(binary.length); binHead.write("BIN\0", 4);
  return Buffer.concat([header, json, binHead, binary]);
}
const groups = [
  { id: "rail.left", center: [-1.3, 1.85, -0.86], capacity: 4, pitch: 0.14, width: 0.56 },
  { id: "rail.right", center: [-0.58, 1.85, -0.86], capacity: 4, pitch: 0.14, width: 0.56 },
  { id: "shelf.shoes", center: [0.94, 0.25, -1.0], capacity: 3, pitch: 0.45, width: 1.35 },
  { id: "shelf.folded", center: [0.94, 1.05, -1.0], capacity: 6, pitch: 0.5, width: 1.5, positions: [[0.44, 1.05, -1.0], [0.94, 1.05, -1.0], [1.44, 1.05, -1.0], [0.44, 1.55, -1.0], [0.94, 1.55, -1.0], [1.44, 1.55, -1.0]] },
  { id: "tray.accessories", center: [-0.85, 0.515, 0.315], capacity: 1, pitch: 0.3, width: 0.45 },
  { id: "stand.outfit", center: [0.25, 0.015, 0.2], capacity: 1, pitch: 0.12, width: 0.65 },
];
const camera = { fov: 38, near: 0.05, far: 40, position: [0, 1.6, 5.4], target: [0, 1.27, -0.6] };
const manifests = [];
for (const modular of [false, true]) {
  const id = modular ? "starter_modular" : "starter_wooden", folder = path.join(publicRoot, "demo/rooms", id);
  if (checkOnly) {
    const manifest = JSON.parse(await readFile(path.join(folder, "manifest.json"), "utf8"));
    if (manifest.id !== id || manifest.glb !== `/demo/rooms/${id}/room.glb` || manifest.poster !== `/demo/rooms/${id}/poster.webp`) throw Error(`Unexpected starter asset path: ${id}`);
    manifests.push(manifest);
    continue;
  }
  await mkdir(folder, { recursive: true });
  const scene = merge(room(modular)), raw = await new GLTFExporter().parseAsync(scene, { binary: true });
  const bytes = embedGrain(Buffer.from(raw)), compressed = gzipSync(bytes, { level: 9, mtime: 0 });
  const bounds = new T.Box3().setFromObject(scene);
  const rights = {
    schemaVersion: 1, author: "Brand.Me original procedural starter environments", created: "2026-10-24", source: "Original parametric furniture, room geometry and grain texture in scripts/assets/starter-environments.mjs", thirdPartyVisualAssets: [], license: "PROPRIETARY", rightsHolder: "Brand.Me, Inc.",
    permittedUses: ["demo display", "3D preview", "room placement", "derivative posters"], productClaims: "Original fictional furnishings. No retailer brand, commercial furniture design or reward entitlement is represented.", generatorDependencies: [{ name: "three", version: "0.182.0", license: "MIT" }],
  };
  const rightsBytes = Buffer.from(JSON.stringify(rights, null, 2) + "\n");
  const files = {};
  for (const [name, content] of [["room.glb", bytes], ["room.glb.gz", compressed], ["rights.json", rightsBytes]]) {
    await writeFile(path.join(folder, name), content); files[name] = { sha256: sha(content), bytes: content.length };
  }
  const manifest = {
    schemaVersion: 1, id, title: modular ? "Modular Studio" : "Oak Starter", revision: "starter-v1", dimensionsMeters: [3.8, 2.8, 2.6],
    collisionBounds: { min: bounds.min.toArray(), max: bounds.max.toArray() }, glb: `/demo/rooms/${id}/room.glb`, poster: `/demo/rooms/${id}/poster.webp`, rights: `/demo/rooms/${id}/rights.json`, units: "meters", up: "+Y", forward: "-Z", lightKelvin: 4300,
    triangleCount: scene.children.reduce((sum, mesh) => sum + mesh.geometry.attributes.position.count / 3, 0), drawCalls: scene.children.length,
    groups, camera, views: [{ id: "room", name: "Room", position: camera.position, target: camera.target }],
    access: { presentationTier: "starter", entitlementAuthority: "none: available starter asset; consumer shell integration pending" },
    qa: { structural: "pending validation", visual: "pending rendering", loader: "not run" }, files,
  };
  manifests.push(manifest);
  await writeFile(path.join(folder, "manifest.json"), JSON.stringify(manifest, null, 2) + "\n");
}

const server = createServer(async (request, response) => {
  try {
    const url = new URL(request.url, "http://localhost"), isTool = url.pathname.startsWith("/tools/") || url.pathname === "/";
    const base = isTool ? toolsDir : publicRoot;
    const filename = url.pathname === "/" ? path.join(toolsDir, "starter-review.html") : path.resolve(base, "." + url.pathname.replace(/^\/tools/, ""));
    if (!filename.startsWith(base + path.sep)) throw Error("Invalid path");
    const types = { ".html": "text/html", ".js": "text/javascript", ".json": "application/json", ".glb": "model/gltf-binary" };
    response.setHeader("Content-Type", types[path.extname(filename)] || "application/octet-stream"); response.end(await readFile(filename));
  } catch { response.writeHead(404); response.end(); }
});
await new Promise((resolve, reject) => { server.once("error", reject); server.listen(0, "127.0.0.1", resolve); });
let browser;
try {
  browser = await chromium.launch({ headless: true, args: ["--no-sandbox", "--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"] });
  for (const manifest of manifests) {
    const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
    const errors = []; page.on("pageerror", (error) => errors.push(error.message));
    await page.goto(`http://127.0.0.1:${server.address().port}/?room=${manifest.id}`);
    await page.waitForFunction(() => window.starterReview?.ready, {}, { timeout: 30000 });
    if (errors.length) throw Error(errors.join("; "));
    const review = await page.evaluate(() => ({ ...window.starterReview, webp: window.starterReview.webp() }));
    const poster = Buffer.from(review.webp.split(",")[1], "base64");
    if (!checkOnly) {
      await writeFile(path.join(publicRoot, manifest.poster), poster);
      manifest.files["poster.webp"] = { sha256: sha(poster), bytes: poster.length };
    }
    manifest.qa = { structural: "generated; run assets:validate", visual: "rendered from declared camera; human approval not claimed", loader: "Chromium / Three GLTFLoader 0.182.0", render: { viewport: "1440x900", triangles: review.triangles, drawCalls: review.calls, shelfGrounding: review.shelfGrounding, renderer: "Chromium software WebGL2; not device performance" } };
    if (!checkOnly) await writeFile(path.join(publicRoot, "demo/rooms", manifest.id, "manifest.json"), JSON.stringify(manifest, null, 2) + "\n");
    await page.close();
  }
} finally {
  try { await browser?.close(); }
  finally { await new Promise((resolve) => server.close(resolve)); }
}
const progression = {
  schemaVersion: 1, status: "presentation-assets-only", consumerShellIntegrated: false,
  rights: "Each room manifest names its rights record.",
  starters: manifests.map((manifest) => ({ id: manifest.id, title: manifest.title, manifest: `/demo/rooms/${manifest.id}/manifest.json`, availableByDefault: true })),
  upgrades: ["walnut_atelier", "limestone_gallery", "garden_studio"].map((id) => ({ id, manifest: `/demo/rooms/${id}/manifest.json`, presentationTier: "earned-upgrade", gate: "Requires authoritative rewards entitlement supplied by the consumer shell; no local points, purchase or unlock authority." })),
  transitions: manifests.flatMap((from) => ["walnut_atelier", "limestone_gallery", "garden_studio"].map((to) => ({ from: from.id, to, placement: "Remap by matching semantic group; capacity overflow goes to Unplaced with item identity retained." }))),
  limits: "Progression is an asset handoff proposal. It does not award points, sell upgrades, lock existing rooms or change shell behavior. Rich 3D remains for the owner; friend projections use the consumer shell's disclosure-filtered 2D view.",
};
if (!checkOnly) await writeFile(path.join(publicRoot, "demo/environment-progression.json"), JSON.stringify(progression, null, 2) + "\n");
console.log(JSON.stringify({ status: checkOnly ? "verified-committed-assets" : "rendered", rooms: manifests.map((manifest) => ({ id: manifest.id, triangles: manifest.triangleCount, drawCalls: manifest.drawCalls, compressedBytes: manifest.files["room.glb.gz"].bytes, render: manifest.qa.render })) }, null, 2));

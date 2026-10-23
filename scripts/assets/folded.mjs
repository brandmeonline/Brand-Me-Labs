import * as T from "three";
import { readFile, writeFile } from "node:fs/promises";
import { createHash } from "node:crypto";
import { fileURLToPath } from "node:url";
import path from "node:path";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const pub = path.join(root, "brandme-frontend/public");

// Closed, curved textile surface with soft superellipse corners and uneven hems.
// These are authored folds, not box stand-ins or a physical drape simulation.
function cloth(parent, material, { width, depth, height, y, phase = 0 }) {
  const positions = [], uvs = [], indices = [], radial = 48, rings = 8;
  for (let j = 0; j <= rings; j++) {
    const v = j / rings, latitude = Math.PI * v;
    const radius = Math.pow(Math.sin(latitude), 0.18);
    for (let i = 0; i <= radial; i++) {
      const a = i / radial * Math.PI * 2, c = Math.cos(a), s = Math.sin(a);
      const wrinkle = Math.sin(a * 7 + phase + v * 2) * 0.0014 * Math.sin(latitude);
      const x = Math.sign(c) * Math.pow(Math.abs(c), 0.27) * width / 2 * radius;
      const z = Math.sign(s) * Math.pow(Math.abs(s), 0.27) * depth / 2 * radius;
      positions.push(x + wrinkle, y + height / 2 * (1 - Math.cos(latitude)) + wrinkle * 0.5, z);
      uvs.push(i / radial, v);
      if (j < rings && i < radial) {
        const k = j * (radial + 1) + i;
        indices.push(k, k + radial + 1, k + 1, k + 1, k + radial + 1, k + radial + 2);
      }
    }
  }
  const geometry = new T.BufferGeometry();
  geometry.setAttribute("position", new T.Float32BufferAttribute(positions, 3));
  geometry.setAttribute("uv", new T.Float32BufferAttribute(uvs, 2));
  geometry.setIndex(indices);
  geometry.computeVertexNormals();
  const result = new T.Mesh(geometry, material);
  parent.add(result);
  return result;
}

function folded(slug, { materials, mesh, tube }) {
  const g = new T.Group();
  g.name = `${slug}-folded-original`;
  const fabric = slug === "jacket" ? materials.olive : slug === "dress" ? materials.violet
    : ["tee", "trousers"].includes(slug) ? materials.cream : materials.linen;
  const seam = fabric.clone();
  seam.name = `${slug} fabric seam`;
  seam.color.multiplyScalar(0.77);
  const thick = slug === "knit" ? 0.018 : slug === "jacket" ? 0.016 : 0.012;
  const width = slug === "trousers" ? 0.255 : 0.32;
  for (let layer = 0; layer < 3; layer++) {
    cloth(g, fabric, { width: width - layer * 0.005, depth: 0.34 - layer * 0.009,
      height: thick, y: layer * thick * 0.78 + 0.002, phase: layer * 1.7 });
    tube(g, [[-width * 0.44, layer * thick * 0.78 + 0.006, 0.166 - layer * 0.004],
      [0, layer * thick * 0.78 + 0.007, 0.172 - layer * 0.004],
      [width * 0.44, layer * thick * 0.78 + 0.006, 0.166 - layer * 0.004]], 0.0009, seam, 24);
  }
  const top = thick * 2.56 + 0.002;
  if (slug === "trousers") {
    cloth(g, fabric, { width: 0.12, depth: 0.29, height: 0.009, y: top - 0.002, phase: 4 }).position.x = 0.061;
    for (const x of [-0.06, 0.06]) tube(g, [[x, top + 0.006, -0.12], [x + 0.003, top + 0.01, 0], [x, top + 0.006, 0.12]], 0.001, seam, 24);
  } else {
    const points = Array.from({ length: 33 }, (_, i) => {
      const a = i / 32 * Math.PI * 2;
      return [Math.cos(a) * 0.05, top + 0.005 + (1 - Math.sin(a)) * 0.004, -0.097 + Math.sin(a) * 0.029];
    });
    tube(g, points, slug === "knit" ? 0.005 : 0.003, seam, 48);
    if (["jacket", "overshirt"].includes(slug)) {
      for (const side of [-1, 1]) {
        const flap = cloth(g, fabric, { width: 0.047, depth: 0.066, height: 0.012, y: top + 0.008 });
        flap.position.set(side * 0.036, 0, -0.077);
        flap.rotation.y = side * 0.45;
      }
      tube(g, [[0, top + 0.003, -0.04], [0, top + 0.003, 0.07], [0, top - 0.002, 0.13]], 0.0014, seam, 24);
      for (const z of [-0.025, 0.025, 0.075, 0.12])
        mesh(new T.SphereGeometry(0.0035, 10, 6), materials.cream, g, [0, top + 0.005, z]).scale.y = 0.45;
    }
    if (slug === "knit") for (let i = -14; i <= 14; i++) {
      const x = i * 0.009;
      tube(g, [[x, top - 0.001, -0.035], [x + 0.001, top + 0.002, 0.04], [x, top - 0.003, 0.13]], 0.0008, seam, 10);
    }
    if (slug === "dress") for (let i = -4; i <= 4; i++) {
      const x = i * 0.029;
      tube(g, [[x, top - 0.001, -0.03], [x + 0.007, top + 0.002, 0.07], [x - 0.004, top - 0.004, 0.14]], 0.001, seam, 18);
    }
  }
  g.position.y = -new T.Box3().setFromObject(g).min.y;
  return g;
}

export async function publishFolded(helpers) {
  const catalog = JSON.parse(await readFile(path.join(pub, "demo/catalog.json")));
  for (const asset of catalog.products.filter(a => !["bag", "sneaker"].includes(a.slug))) {
    const dir = path.join(pub, path.dirname(asset.glb));
    const result = await helpers.exportAsset(folded(asset.slug, helpers), dir, false, "folded.glb");
    asset.folded = {
      revision: "folded-original-v1", glb: `${path.dirname(asset.glb)}/folded.glb`,
      poster: `${path.dirname(asset.glb)}/folded.webp`, fidelity: "P1",
      fidelityLabel: "Approximate 3D", pivot: "grounded_bottom_center",
      dimensionsMeters: result.dimensions, collisionBounds: result.bounds,
      triangleCount: result.triangles, drawCalls: result.drawCalls,
      source: "Original curved layered textile surfaces in scripts/assets/folded.mjs",
      rights: asset.rights, use: "Folded shelf display; not a drape or physical fit simulation",
      qa: { loader: "pending", visual: "pending", roomPlacement: "semantic_shelf_v2; verification required" },
    };
    for (const name of ["folded.glb", "folded.glb.gz"]) {
      const b = await readFile(path.join(dir, name));
      asset.files[name] = { bytes: b.length, sha256: createHash("sha256").update(b).digest("hex") };
    }
    await writeFile(path.join(dir, "manifest.json"), JSON.stringify(asset, null, 2) + "\n");
  }
  const serialized = JSON.stringify(catalog, null, 2) + "\n";
  await writeFile(path.join(pub, "demo/catalog.json"), serialized);
  await writeFile(path.join(root, "brandme-frontend/features/spatial/generated-catalog.json"), serialized);
  console.log("Generated six original folded variants; run review.mjs --folded.");
}

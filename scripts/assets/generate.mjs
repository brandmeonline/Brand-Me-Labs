import * as T from "three";
import { RoundedBoxGeometry } from "three/addons/geometries/RoundedBoxGeometry.js";
import { mergeGeometries } from "three/addons/utils/BufferGeometryUtils.js";
import { GLTFExporter } from "three/addons/exporters/GLTFExporter.js";
import { USDZExporter } from "three/addons/exporters/USDZExporter.js";
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { createHash } from "node:crypto";
import { deflateSync, gzipSync } from "node:zlib";
import { fileURLToPath } from "node:url";
import path from "node:path";

const root = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../..",
);
const publicRoot = path.join(root, "brandme-frontend/public");
const demo = JSON.parse(
  await readFile(
    path.join(root, "docs/design/brandme/contracts/demo-scenario.json"),
  ),
);
const output = path.join(publicRoot, "demo");
const sha = (bytes) => createHash("sha256").update(bytes).digest("hex");
// Three's export API uses FileReader even when its input is an in-memory Blob.
globalThis.FileReader = class {
  readAsArrayBuffer(blob) {
    blob.arrayBuffer().then((result) => {
      this.result = result;
      this.onloadend?.();
    });
  }
  readAsDataURL(blob) {
    blob.arrayBuffer().then((result) => {
      this.result = `data:${blob.type};base64,${Buffer.from(result).toString("base64")}`;
      this.onloadend?.();
    });
  }
};
const mat = (name, color, roughness = 0.82, metalness = 0) =>
  new T.MeshStandardMaterial({
    name,
    color,
    roughness,
    metalness,
    side: T.DoubleSide,
  });
const materials = {
  walnut: mat("walnut_grain", "#674734"),
  oak: mat("ash_grain", "#BFAB89"),
  plaster: mat("plaster", "#E9DFCC"),
  stone: mat("limestone", "#D9D0BD"),
  green: mat("sage_plaster", "#87917B"),
  brass: mat("aged_brass", "#9E8355", 0.34, 0.7),
  steel: mat("brushed_steel", "#9FA6A4", 0.35, 0.8),
  ink: mat("dark_metal", "#333932", 0.42, 0.55),
  linen: mat("fabric_linen", "#D6C8B3"),
  cream: mat("fabric_cream", "#EEE6D7"),
  violet: mat("fabric_iris", "#62527F"),
  olive: mat("fabric_olive", "#526447"),
  tobacco: mat("leather_tobacco", "#81533D", 0.62),
  sole: mat("rubber_ivory", "#DDD6C5"),
  leaf: mat("leaf", "#607557"),
  mirror: mat("mirror_approximation", "#B0B9B1", 0.2, 0.65),
};
function mesh(g, m, parent, position = [0, 0, 0], rotation = [0, 0, 0]) {
  const o = new T.Mesh(g, m);
  o.position.set(...position);
  o.rotation.set(...rotation);
  o.castShadow = true;
  o.receiveShadow = true;
  parent.add(o);
  return o;
}
function box(parent, size, position, material, radius = 0.015) {
  return mesh(
    new RoundedBoxGeometry(...size, 2, radius),
    material,
    parent,
    position,
  );
}
function tube(parent, points, radius, material, segments = 20) {
  return mesh(
    new T.TubeGeometry(
      new T.CatmullRomCurve3(points.map((p) => new T.Vector3(...p))),
      segments,
      radius,
      6,
      false,
    ),
    material,
    parent,
  );
}
function rod(parent, from, to, radius, material) {
  return tube(parent, [from, to], radius, material, 1);
}
function sphere(parent, center, scale, material, segments = 12) {
  const o = mesh(
    new T.SphereGeometry(1, segments, 8),
    material,
    parent,
    center,
  );
  o.scale.set(...scale);
  return o;
}

// Lofted, open cloth surfaces: silhouette, asymmetric folds, curved hems and real depth.
// Each ring is [centerX, y, centerZ, halfWidth, halfDepth]. No box garments.
function loft(parent, rings, material, radial = 32, fold = 0.008, phase = 0) {
  const vertices = [],
    uv = [],
    indices = [];
  for (let j = 0; j < rings.length; j++) {
    const [x, y, z, w, d] = rings[j];
    for (let i = 0; i <= radial; i++) {
      const a = (i / radial) * Math.PI * 2;
      const ripple =
        fold *
        (Math.sin(a * 9 + phase + j * 0.32) +
          0.35 * Math.sin(a * 17 + j * 0.45));
      vertices.push(
        x + Math.cos(a) * (w + ripple),
        y + 0.004 * Math.cos(a * 4 + j * 0.8),
        z + Math.sin(a) * (d + ripple * 0.7),
      );
      uv.push(i / radial, j / (rings.length - 1));
      if (j < rings.length - 1 && i < radial) {
        const k = j * (radial + 1) + i;
        indices.push(
          k,
          k + 1,
          k + radial + 1,
          k + 1,
          k + radial + 2,
          k + radial + 1,
        );
      }
    }
  }
  const g = new T.BufferGeometry();
  g.setAttribute("position", new T.Float32BufferAttribute(vertices, 3));
  g.setAttribute("uv", new T.Float32BufferAttribute(uv, 2));
  g.setIndex(indices);
  g.computeVertexNormals();
  return mesh(g, material, parent);
}
function panel(parent, points, material) {
  const shape = new T.Shape();
  shape.moveTo(points[0][0], points[0][1]);
  for (const p of points.slice(1)) shape.lineTo(p[0], p[1]);
  shape.closePath();
  return mesh(
    new T.ExtrudeGeometry(shape, {
      depth: 0.009,
      bevelEnabled: true,
      bevelSize: 0.003,
      bevelThickness: 0.003,
      bevelSegments: 2,
      steps: 1,
    }),
    material,
    parent,
    [0, 0, 0.087],
  );
}
function hanger(g) {
  tube(
    g,
    [
      [0, 0, 0],
      [0.035, 0.042, 0],
      [0.03, 0.087, 0],
      [0, 0.104, 0],
      [-0.025, 0.08, 0],
    ],
    0.007,
    materials.brass,
    14,
  );
  tube(
    g,
    [
      [0, 0, 0],
      [-0.19, -0.105, 0],
      [-0.24, -0.14, 0],
      [0.24, -0.14, 0],
      [0.19, -0.105, 0],
      [0, 0, 0],
    ],
    0.011,
    materials.oak,
    24,
  );
}
function garment(kind, low = false) {
  const g = new T.Group();
  g.name = kind;
  const n = low ? 20 : 48;
  const color = {
    overshirt: materials.linen,
    jacket: materials.olive,
    tee: materials.cream,
    knit: materials.linen,
    dress: materials.violet,
    trousers: materials.cream,
  }[kind];
  if (["overshirt", "jacket", "tee", "knit"].includes(kind)) {
    hanger(g);
    const long = kind !== "tee",
      structured = kind === "jacket";
    loft(
      g,
      [
        [0, -0.13, 0, 0.105, 0.064],
        [0, -0.18, 0, 0.235, 0.075],
        [0, -0.24, 0, 0.245, 0.084],
        [0, -0.36, 0, 0.228, 0.09],
        [0, -0.5, 0, 0.22, 0.088],
        [0, -0.65, 0, 0.235, 0.096],
        [0, -0.79, 0, 0.243, 0.092],
      ],
      color,
      n,
      structured ? 0.003 : 0.009,
    );
    for (const s of [-1, 1]) {
      loft(
        g,
        [
          [s * 0.212, -0.19, 0, 0.076, 0.081],
          [s * 0.278, -0.245, 0, 0.078, 0.075],
          [s * 0.325, -0.34, 0.005, 0.071, 0.069],
          ...(long
            ? [
                [s * 0.373, -0.47, 0.009, 0.066, 0.063],
                [s * 0.4, -0.6, 0.008, 0.057, 0.053],
                [s * 0.404, -0.7, 0.01, 0.054, 0.049],
              ]
            : []),
        ],
        color,
        n,
        0.005,
        s,
      );
      if (long)
        loft(
          g,
          [
            [s * 0.404, -0.668, 0.01, 0.055, 0.052],
            [s * 0.404, -0.713, 0.01, 0.055, 0.052],
          ],
          color,
          n,
          0,
        );
      if (kind === "jacket" || kind === "overshirt") {
        panel(
          g,
          [
            [s * 0.06, -0.4],
            [s * 0.185, -0.4],
            [s * 0.185, -0.52],
            [s * 0.12, -0.54],
            [s * 0.06, -0.52],
          ],
          color,
        );
        panel(
          g,
          [
            [s * 0.06, -0.393],
            [s * 0.185, -0.393],
            [s * 0.175, -0.428],
            [s * 0.075, -0.428],
          ],
          color,
        );
      }
    }
    if (kind === "tee" || kind === "knit") {
      loft(
        g,
        [
          [0, -0.126, 0, 0.095, 0.064],
          [0, -0.149, 0, 0.1, 0.068],
        ],
        color,
        n,
        0,
      );
      loft(
        g,
        [
          [0, -0.76, 0, 0.243, 0.094],
          [0, -0.797, 0, 0.243, 0.094],
        ],
        color,
        n,
        0,
      );
    } else {
      for (const s of [-1, 1])
        panel(
          g,
          [
            [s * 0.025, -0.131],
            [s * 0.11, -0.14],
            [s * 0.158, -0.216],
            [s * 0.071, -0.255],
            [s * 0.015, -0.18],
          ],
          color,
        );
      rod(g, [0, -0.19, 0.099], [0, -0.765, 0.103], 0.008, color);
      for (let i = 0; i < 6; i++)
        sphere(
          g,
          [0.018, -0.25 - i * 0.088, 0.111],
          [0.009, 0.009, 0.004],
          materials.tobacco,
        );
    }
    if (kind === "knit")
      for (let i = -10; i <= 10; i++)
        tube(
          g,
          [
            [i * 0.02, -0.25, 0.083],
            [i * 0.02, -0.48, 0.095],
            [i * 0.022, -0.75, 0.104],
          ],
          0.0019,
          materials.cream,
          5,
        );
  } else if (kind === "dress") {
    hanger(g);
    loft(
      g,
      [
        [0, -0.16, 0, 0.14, 0.06],
        [0, -0.26, 0, 0.18, 0.088],
        [0, -0.38, 0, 0.157, 0.073],
        [0, -0.5, 0, 0.131, 0.061],
        [0, -0.65, 0, 0.18, 0.09],
        [0, -0.86, 0, 0.233, 0.118],
        [0, -1.08, 0, 0.282, 0.154],
        [0, -1.35, 0, 0.33, 0.184],
      ],
      color,
      n,
      0.009,
    );
    for (const s of [-1, 1])
      tube(
        g,
        [
          [s * 0.1, -0.24, 0.058],
          [s * 0.115, -0.139, 0.005],
          [s * 0.14, -0.235, -0.055],
        ],
        0.022,
        color,
        10,
      );
    loft(
      g,
      [
        [0, -0.49, 0, 0.135, 0.066],
        [0, -0.521, 0, 0.14, 0.071],
      ],
      materials.violet,
      n,
      0.001,
    );
  } else if (kind === "trousers") {
    hanger(g);
    loft(
      g,
      [
        [0, -0.16, 0, 0.206, 0.091],
        [0, -0.21, 0, 0.212, 0.098],
        [0, -0.34, 0, 0.223, 0.1],
        [0, -0.42, 0, 0.2, 0.088],
      ],
      color,
      n,
      0.003,
    );
    for (const s of [-1, 1]) {
      loft(
        g,
        [
          [s * 0.108, -0.33, 0, 0.11, 0.094],
          [s * 0.114, -0.43, 0, 0.105, 0.087],
          [s * 0.125, -0.6, 0, 0.101, 0.081],
          [s * 0.136, -0.8, 0, 0.103, 0.078],
          [s * 0.148, -1.06, 0, 0.107, 0.074],
          [s * 0.15, -1.16, 0, 0.11, 0.074],
        ],
        color,
        n,
        0.006,
      );
      tube(
        g,
        [
          [s * 0.115, -0.25, 0.1],
          [s * 0.128, -0.5, 0.09],
          [s * 0.145, -0.83, 0.085],
          [s * 0.157, -1.153, 0.08],
        ],
        0.0025,
        materials.linen,
        18,
      );
      tube(
        g,
        [
          [s * 0.21, -0.23, 0.04],
          [s * 0.17, -0.3, 0.093],
          [s * 0.145, -0.37, 0.099],
        ],
        0.003,
        materials.linen,
        10,
      );
    }
    loft(
      g,
      [
        [0, -0.16, 0, 0.21, 0.095],
        [0, -0.2, 0, 0.213, 0.1],
      ],
      color,
      n,
      0,
    );
    sphere(g, [0.019, -0.18, 0.103], [0.009, 0.009, 0.004], materials.tobacco);
  } else if (kind === "sneaker") {
    for (const s of [-1, 1]) {
      const shoe = new T.Group();
      g.add(shoe);
      shoe.position.x = s * 0.105;
      shoe.rotation.y = -s * 0.09;
      loft(
        shoe,
        [
          [0, 0.022, 0, 0.086, 0.167],
          [0, 0.049, 0, 0.087, 0.169],
          [0, 0.065, 0, 0.084, 0.165],
          [0, 0.075, 0, 0.08, 0.158],
        ],
        materials.sole,
        n,
        0,
      );
      loft(
        shoe,
        [
          [0, 0.069, 0, 0.079, 0.157],
          [0, 0.1, -0.008, 0.074, 0.148],
          [0, 0.14, -0.028, 0.067, 0.126],
          [0, 0.17, -0.071, 0.061, 0.08],
        ],
        materials.cream,
        n,
        0.001,
      );
      loft(
        shoe,
        [
          [0, 0.174, -0.07, 0.054, 0.062],
          [0, 0.155, -0.07, 0.047, 0.057],
        ],
        materials.linen,
        n,
        0,
      );
      sphere(shoe, [0, 0.141, 0.033], [0.05, 0.022, 0.075], materials.cream, n);
      for (let i = 0; i < 5; i++)
        rod(
          shoe,
          [-0.035, 0.157 - i * 0.007, 0.01 + i * 0.019],
          [0.035, 0.157 - i * 0.007, 0.021 + i * 0.019],
          0.003,
          materials.linen,
        );
      tube(
        shoe,
        [
          [-0.071, 0.095, 0.088],
          [-0.078, 0.1, 0.035],
          [-0.07, 0.12, -0.045],
          [-0.061, 0.141, -0.118],
        ],
        0.0028,
        materials.linen,
        15,
      );
    }
  } else if (kind === "bag") {
    loft(
      g,
      [
        [0, 0.014, 0, 0.15, 0.066],
        [0, 0.04, 0, 0.173, 0.077],
        [0, 0.16, 0, 0.178, 0.078],
        [0, 0.27, 0, 0.165, 0.07],
        [0, 0.29, 0, 0.155, 0.062],
      ],
      materials.tobacco,
      n,
      0.001,
    );
    for (const z of [-0.05, 0.055])
      tube(
        g,
        [
          [-0.112, 0.273, z],
          [-0.09, 0.4, z],
          [0, 0.46, z],
          [0.09, 0.4, z],
          [0.112, 0.273, z],
        ],
        0.012,
        materials.tobacco,
        30,
      );
    tube(
      g,
      [
        [-0.15, 0.28, 0.07],
        [-0.17, 0.06, 0.074],
        [0, 0.033, 0.08],
        [0.17, 0.06, 0.074],
        [0.15, 0.28, 0.07],
      ],
      0.0025,
      materials.linen,
      25,
    );
    box(g, [0.036, 0.026, 0.008], [0, 0.254, 0.074], materials.brass, 0.004);
  }
  return g;
}
function plant(parent, pos, height = 0.75) {
  loft(
    parent,
    [
      [pos[0], pos[1], pos[2], 0.12, 0.12],
      [pos[0], pos[1] + 0.24, pos[2], 0.15, 0.15],
    ],
    materials.stone,
    20,
    0,
  );
  for (let i = 0; i < 9; i++) {
    const a = i * 2.4,
      top = [
        pos[0] + Math.sin(a) * 0.23,
        pos[1] + height * (0.65 + i / 24),
        pos[2] + Math.cos(a) * 0.19,
      ];
    rod(parent, [pos[0], pos[1] + 0.18, pos[2]], top, 0.006, materials.leaf);
    const o = sphere(parent, top, [0.07, 0.19, 0.012], materials.leaf);
    o.rotation.set(0.4, a, 0.6);
  }
}
function room(def) {
  const g = new T.Group();
  g.name = def.id;
  const [w, d, h] = def.dimensions_m,
    wal = def.id === "walnut_atelier",
    garden = def.id === "garden_studio";
  const wood = wal ? materials.walnut : materials.oak,
    metal = wal ? materials.brass : materials.steel;
  const wall = garden
    ? materials.green
    : wal
      ? materials.plaster
      : materials.stone;
  box(g, [w, 0.09, d], [0, -0.045, 0], wal ? materials.oak : materials.stone);
  box(g, [w, h, 0.085], [0, h / 2, -d / 2], wall);
  box(g, [0.085, h, d], [-w / 2, h / 2, 0], wall);
  // Right side is cut away for all named cameras; the window jamb still defines the room.
  box(g, [0.09, h, 0.2], [w / 2, h / 2, -d / 2 + 0.1], wall);
  box(g, [w, 0.05, 0.065], [0, 0.035, -d / 2 + 0.075], wood);
  if (wal) {
    for (let x = -w / 2 + 0.12; x < w / 2; x += 0.16)
      box(g, [0.027, h - 0.18, 0.036], [x, h / 2, -d / 2 + 0.075], wood, 0.005);
    for (const s of [-1, 1]) {
      box(g, [1.5, 0.08, 0.51], [s * 1.45, 2.03, -0.92], wood);
      for (const x of [s * 1.45 - 0.74, s * 1.45 + 0.74])
        box(g, [0.065, 1.99, 0.49], [x, 1.04, -0.92], wood);
      rod(
        g,
        [s * 1.45 - 0.71, 1.75, -0.65],
        [s * 1.45 + 0.71, 1.75, -0.65],
        0.012,
        metal,
      );
      for (const y of [0.23, 0.38]) {
        box(g, [1.38, 0.13, 0.48], [s * 1.45, y, -0.91], wood);
        rod(
          g,
          [s * 1.45 - 0.15, y, -0.659],
          [s * 1.45 + 0.15, y, -0.659],
          0.005,
          metal,
        );
      }
    }
    for (const y of [0.2, 0.57, 1.01, 1.47])
      box(g, [1.27, 0.07, 0.48], [0, y, -1.17], wood);
  } else if (garden) {
    for (const x of [-2.15, -0.55])
      rod(g, [x, 0.02, -0.75], [x, 2.05, -0.75], 0.017, metal);
    rod(g, [-2.15, 1.75, -0.65], [-0.55, 1.75, -0.65], 0.014, metal);
    box(g, [1.74, 0.1, 0.56], [-1.35, 0.14, -0.87], wood);
    for (const y of [0.23, 0.62, 1.05, 1.49, 1.94])
      box(g, [1.37, 0.058, 0.52], [1.34, y, -1.28], wood);
    for (const x of [0.62, 2.05])
      box(g, [0.06, 2.12, 0.55], [x, 1.06, -1.29], wood);
    box(g, [1.2, 0.13, 0.53], [0.15, 0.43, 0.56], materials.linen, 0.06);
    for (const x of [-0.3, 0.6])
      box(g, [0.07, 0.38, 0.4], [x, 0.19, 0.56], wood);
    plant(g, [-1.9, 0.02, 0.55], 1.24);
  } else {
    for (const x of [-1.65, 0, 1.65]) {
      for (const dx of [-0.66, 0.66])
        box(g, [0.065, 2.32, 0.56], [x + dx, 1.16, -1.35], wood);
      box(g, [1.39, 0.07, 0.56], [x, 2.33, -1.35], wood);
      rod(g, [x - 0.64, 1.75, -0.85], [x + 0.64, 1.75, -0.85], 0.012, metal);
      box(g, [1.22, 0.21, 0.5], [x, 0.14, -1.25], materials.stone, 0.025);
    }
    box(g, [0.84, 2.1, 0.035], [0, 1.22, -1.83], materials.mirror, 0.06);
    box(g, [0.7, 0.22, 0.65], [0, 0.11, 0.5], materials.stone, 0.035);
  }
  // Low central display keeps the silhouettes visible from the exact 38° camera.
  if (!garden) {
    mesh(
      new T.CylinderGeometry(0.27, 0.31, 0.055, 40),
      metal,
      g,
      [0, 0.027, -0.1],
    );
    rod(g, [0, 0.04, -0.1], [0, 1.66, -0.1], 0.016, metal);
    rod(g, [-0.31, 1.66, -0.1], [0.31, 1.66, -0.1], 0.012, metal);
  }
  box(g, [0.53, 0.055, 0.37], [1.45, 0.8, 0.4], wood);
  for (const x of [1.24, 1.66])
    for (const z of [0.26, 0.54]) rod(g, [x, 0, z], [x, 0.79, z], 0.013, metal);
  box(g, [0.43, 0.025, 0.28], [1.45, 0.84, 0.4], materials.linen);
  if (!garden) plant(g, [w / 2 - 0.32, 0, -d / 2 + 0.31], 0.73);
  return g;
}
function mergeByMaterial(group) {
  group.updateMatrixWorld(true);
  const buckets = new Map();
  group.traverse((o) => {
    if (!o.isMesh) return;
    let geo = o.geometry.clone();
    if (geo.index) geo = geo.toNonIndexed();
    geo.applyMatrix4(o.matrixWorld);
    if (!geo.getAttribute("uv"))
      geo.setAttribute(
        "uv",
        new T.Float32BufferAttribute(
          new Float32Array(geo.getAttribute("position").count * 2),
          2,
        ),
      );
    const list = buckets.get(o.material) || [];
    list.push(geo);
    buckets.set(o.material, list);
  });
  const result = new T.Group();
  result.name = group.name;
  for (const [material, parts] of buckets) {
    const m = mesh(mergeGeometries(parts), material, result);
    m.name = material.name;
  }
  return result;
}
// Small original repeatable PBR maps embedded into the GLB; no external texture URLs.
function crc32(b) {
  let c = ~0;
  for (const v of b) {
    c ^= v;
    for (let i = 0; i < 8; i++) c = (c >>> 1) ^ (c & 1 ? 0xedb88320 : 0);
  }
  return (c ^ ~0) >>> 0;
}
function png(rgb, size = 64) {
  const chunk = (type, data) => {
    const t = Buffer.from(type),
      n = Buffer.alloc(4),
      c = Buffer.alloc(4);
    n.writeUInt32BE(data.length);
    c.writeUInt32BE(crc32(Buffer.concat([t, data])));
    return Buffer.concat([n, t, data, c]);
  };
  const head = Buffer.alloc(13);
  head.writeUInt32BE(size);
  head.writeUInt32BE(size, 4);
  head[8] = 8;
  head[9] = 2;
  const rows = Buffer.alloc(size * (size * 3 + 1));
  for (let y = 0; y < size; y++)
    rgb.copy(rows, y * (size * 3 + 1) + 1, y * size * 3, (y + 1) * size * 3);
  return Buffer.concat([
    Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]),
    chunk("IHDR", head),
    chunk("IDAT", deflateSync(rows)),
    chunk("IEND", Buffer.alloc(0)),
  ]);
}
function pbrMaps(glb) {
  const jsonLength = glb.readUInt32LE(12),
    j = JSON.parse(glb.subarray(20, 20 + jsonLength).toString());
  let bin = glb.subarray(28 + jsonLength);
  j.images = [];
  j.textures = [];
  j.samplers = [
    { magFilter: 9729, minFilter: 9987, wrapS: 10497, wrapT: 10497 },
  ];
  const append = (bytes) => {
    const pad = (4 - (bin.length % 4)) % 4;
    bin = Buffer.concat([bin, Buffer.alloc(pad)]);
    const v = j.bufferViews.length;
    j.bufferViews.push({
      buffer: 0,
      byteOffset: bin.length,
      byteLength: bytes.length,
    });
    bin = Buffer.concat([bin, bytes]);
    j.images.push({ bufferView: v, mimeType: "image/png" });
    j.textures.push({ sampler: 0, source: j.images.length - 1 });
    return j.textures.length - 1;
  };
  for (const m of j.materials) {
    if (!/fabric|grain|limestone/.test(m.name)) continue;
    const rough = Buffer.alloc(64 * 64 * 3),
      normal = Buffer.alloc(64 * 64 * 3),
      base = Buffer.alloc(64 * 64 * 3);
    for (let y = 0; y < 64; y++)
      for (let x = 0; x < 64; x++) {
        const p = (y * 64 + x) * 3,
          f = m.name.includes("grain")
            ? Math.sin(x * 0.8 + Math.sin(y * 0.1))
            : Math.sin(x * 2.4) * Math.cos(y * 2.4);
        rough[p] = 255;
        rough[p + 1] = 220 + Math.round(f * 15);
        rough[p + 2] = 0;
        normal[p] = 128 + Math.round(f * 8);
        normal[p + 1] = 128 + Math.round(Math.cos(y * 1.8) * 5);
        normal[p + 2] = 254;
        base[p] = base[p + 1] = base[p + 2] = 235 + Math.round(f * 16);
      }
    m.pbrMetallicRoughness.baseColorTexture = { index: append(png(base)) };
    m.pbrMetallicRoughness.metallicRoughnessTexture = {
      index: append(png(rough)),
    };
    m.normalTexture = { index: append(png(normal)), scale: 0.3 };
  }
  bin = Buffer.concat([bin, Buffer.alloc((4 - (bin.length % 4)) % 4)]);
  j.buffers[0].byteLength = bin.length;
  let data = Buffer.from(JSON.stringify(j));
  data = Buffer.concat([data, Buffer.alloc((4 - (data.length % 4)) % 4, 32)]);
  const header = Buffer.alloc(20);
  header.write("glTF");
  header.writeUInt32LE(2, 4);
  header.writeUInt32LE(28 + data.length + bin.length, 8);
  header.writeUInt32LE(data.length, 12);
  header.write("JSON", 16);
  const bh = Buffer.alloc(8);
  bh.writeUInt32LE(bin.length);
  bh.write("BIN\0", 4);
  return Buffer.concat([header, data, bh, bin]);
}
const slotsFor = (id) => {
  const original = demo.walnut_anchor_groups.map((a) => ({
    id: a.id,
    center: a.center_m,
    capacity: a.slots || 12,
    pitch: a.pitch_m || 0.12,
    width: a.width_m || 1.1,
  }));
  if (id === "garden_studio")
    return original
      .filter((a) => a.id !== "rail.right" && a.id !== "stand.outfit")
      .map((a) => ({
        ...a,
        center:
          a.id === "shelf.folded"
            ? [1.34, 1.05, -1.15]
            : a.id === "shelf.shoes"
              ? [-1.35, 0.24, -0.87]
              : a.center,
      }));
  if (id === "limestone_gallery")
    return original.map((a) => ({
      ...a,
      center:
        a.id === "rail.left"
          ? [-1.65, 1.75, -0.85]
          : a.id === "rail.right"
            ? [1.65, 1.75, -0.85]
            : a.center,
    }));
  return original;
};
async function exportAsset(group, dir, isRoom = false) {
  const optimized = mergeByMaterial(group);
  const raw = Buffer.from(
    await new GLTFExporter().parseAsync(optimized, {
      binary: true,
      onlyVisible: true,
    }),
  );
  const bytes = pbrMaps(raw);
  await mkdir(dir, { recursive: true });
  const name = isRoom ? "room.glb" : "lod0.glb";
  await writeFile(path.join(dir, name), bytes);
  await writeFile(
    path.join(dir, name + ".gz"),
    gzipSync(bytes, { level: 9, mtime: 0 }),
  );
  const bounds = new T.Box3().setFromObject(optimized);
  let triangles = 0;
  optimized.traverse((o) => {
    if (o.isMesh) triangles += o.geometry.attributes.position.count / 3;
  });
  return {
    group: optimized,
    bytes,
    triangles,
    drawCalls: optimized.children.length,
    bounds: { min: bounds.min.toArray(), max: bounds.max.toArray() },
    dimensions: bounds.getSize(new T.Vector3()).toArray(),
  };
}
await mkdir(output, { recursive: true });
const rights = {
  schemaVersion: 1,
  author: "Brand.Me procedural asset pipeline",
  created: "2026-10-05",
  source:
    "Original parametric geometry and textures in scripts/assets/generate.mjs",
  thirdPartyVisualAssets: [],
  license: "PROPRIETARY",
  rightsHolder: "Brand.Me, Inc.",
  permittedUses: [
    "demo display",
    "3D preview",
    "room placement",
    "derivative posters",
  ],
  productClaims:
    "Fictional products; approximate visualization. No brand authenticity, physical measurements, manufacturing or calibrated fit claims.",
  generatorDependencies: [
    { name: "three", version: "0.182.0", license: "MIT" },
  ],
};
await writeFile(
  path.join(output, "rights.json"),
  JSON.stringify(rights, null, 2) + "\n",
);
const catalog = [];
for (const p of [
  ...demo.products,
  {
    id: "demo-tee",
    title: "Quiet Cotton Tee",
    category: "top",
    required_assets: { glb: "/demo/garments/tee/lod0.glb" },
  },
  {
    id: "demo-knit",
    title: "Ribbed Oat Knit",
    category: "top",
    required_assets: { glb: "/demo/garments/knit/lod0.glb" },
  },
]) {
  const slug = p.required_assets.glb.split("/")[3],
    base = `/demo/garments/${slug}`,
    dir = path.join(publicRoot, base);
  const high = await exportAsset(garment(slug), dir);
  const low = mergeByMaterial(garment(slug, true));
  const lowBytes = pbrMaps(
    Buffer.from(await new GLTFExporter().parseAsync(low, { binary: true })),
  );
  await writeFile(path.join(dir, "lod1.glb"), lowBytes);
  await writeFile(
    path.join(dir, "lod1.glb.gz"),
    gzipSync(lowBytes, { level: 9, mtime: 0 }),
  );
  // Native USDZ carries the same geometry and colors. PBR microtextures are GLB-only in this revision.
  const native = high.group.clone(true);
  native.traverse((o) => {
    if (o.isMesh) {
      o.material = o.material.clone();
      o.material.side = T.FrontSide;
    }
  });
  await writeFile(
    path.join(dir, "preview.usdz"),
    Buffer.from(await new USDZExporter().parseAsync(native)),
  );
  const manifest = {
    schemaVersion: 1,
    id: p.id,
    slug,
    title: p.title,
    category: p.category,
    revision: "original-v1",
    fidelity: "P1",
    fidelityLabel: "Approximate 3D",
    sourceProductRevision: "fictional-2026-10-05",
    glb: `${base}/lod0.glb`,
    lowGlb: `${base}/lod1.glb`,
    usdz: `${base}/preview.usdz`,
    poster: `${base}/poster.webp`,
    rights: "/demo/rights.json",
    dimensionsMeters: high.dimensions,
    pivot: ["sneaker", "bag"].includes(slug)
      ? "grounded_center"
      : "hanger_hook",
    collisionBounds: high.bounds,
    displayScaleBounds: [0.65, 1.25],
    units: "meters",
    up: "+Y",
    forward: "-Z",
    triangleCount: high.triangles,
    drawCalls: high.drawCalls,
    compression: {
      geometry: "uncompressed portable fallback",
      transport: "gzip sidecar",
      textures: "embedded original PNG PBR maps; no external references",
      native: "USDZ geometry and base colors; microtextures omitted",
    },
    physicalScale: "approximate; not a calibrated product dimension",
    rig: null,
    qa: {
      structural: "pending validation",
      visual: "pending camera review",
      nativeDevice: "not_run",
    },
    files: {},
  };
  for (const name of [
    "lod0.glb",
    "lod0.glb.gz",
    "lod1.glb",
    "lod1.glb.gz",
    "preview.usdz",
  ]) {
    const b = await readFile(path.join(dir, name));
    manifest.files[name] = { sha256: sha(b), bytes: b.length };
  }
  await writeFile(
    path.join(dir, "manifest.json"),
    JSON.stringify(manifest, null, 2) + "\n",
  );
  catalog.push(manifest);
}
const rooms = [];
for (const r of demo.rooms) {
  const dir = path.join(publicRoot, path.dirname(r.required_glb));
  const result = await exportAsset(room(r), dir, true);
  const manifest = {
    schemaVersion: 1,
    id: r.id,
    title: r.name,
    revision: "original-v1",
    dimensionsMeters: r.dimensions_m,
    collisionBounds: result.bounds,
    glb: r.required_glb,
    poster: r.required_poster,
    rights: "/demo/rights.json",
    units: "meters",
    up: "+Y",
    forward: "-Z",
    lightKelvin: r.light_kelvin,
    triangleCount: result.triangles,
    drawCalls: result.drawCalls,
    groups: slotsFor(r.id),
    camera: {
      fov: 38,
      near: 0.05,
      far: 40,
      position: [0, 1.55, 4.8],
      target: [0, 1.35, 0],
    },
    views: [
      {
        id: "room",
        name: "Room",
        position: [0, 1.55, 4.8],
        target: [0, 1.35, 0],
      },
      {
        id: "rail",
        name: "Work rail",
        position: [-1.05, 1.6, 2.3],
        target: [-1.4, 1.3, -0.65],
      },
      {
        id: "details",
        name: "Details",
        position: [1.8, 1.5, 2.5],
        target: [1.45, 1, 0.1],
      },
    ],
    mirror: "Static tinted reflective material; not a live mirror",
    qa: { structural: "pending validation", visual: "pending camera review" },
    files: {},
  };
  for (const name of ["room.glb", "room.glb.gz"]) {
    const b = await readFile(path.join(dir, name));
    manifest.files[name] = { sha256: sha(b), bytes: b.length };
  }
  await writeFile(
    path.join(dir, "manifest.json"),
    JSON.stringify(manifest, null, 2) + "\n",
  );
  rooms.push(manifest);
}
await writeFile(
  path.join(output, "catalog.json"),
  JSON.stringify(
    { schemaVersion: 1, fictional: true, products: catalog, rooms },
    null,
    2,
  ) + "\n",
);
await writeFile(
  path.join(root, "brandme-frontend/features/spatial/generated-catalog.json"),
  await readFile(path.join(root, "brandme-frontend/public/demo/catalog.json")),
);
console.log(
  `Generated ${rooms.length} rooms and ${catalog.length} original garment sets. Run assets:review for rendered posters, then assets:validate.`,
);

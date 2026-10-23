import { allAssets, makePlacement } from "./catalog";
import type {
  Asset,
  ClosetSnapshot,
  Placement,
  SemanticGroup,
  Vector3,
} from "./types";

type Subject = { id?: string; assetSlug: string | null };
type Bounds = { min: Vector3; max: Vector3 };
// A photo billboard uses the same dimensions/offset as SceneCanvas.PhotoDisplay.
const photoBounds: Bounds = {
  min: [-0.275, -0.7, 0.02],
  max: [0.275, 0, 0.02],
};
function worldBounds(subject: Subject, placement: Placement): Bounds {
  const asset = allAssets.find((a) => a.slug === subject.assetSlug) as
    | (Asset & { collisionBounds?: Bounds })
    | undefined;
  const bounds = asset?.collisionBounds ?? photoBounds;
  const min: Vector3 = [Infinity, Infinity, Infinity],
    max: Vector3 = [-Infinity, -Infinity, -Infinity];
  const [qx, qy, qz, qw] = placement.rotationQuaternion;
  for (let corner = 0; corner < 8; corner++) {
    const [x, y, z] = bounds.min.map(
      (v, i) =>
        ((corner >> i) & 1 ? bounds.max[i] : v) * placement.uniformScale,
    );
    const tx = 2 * (qy * z - qz * y),
      ty = 2 * (qz * x - qx * z),
      tz = 2 * (qx * y - qy * x);
    const p = [
      x + qw * tx + qy * tz - qz * ty,
      y + qw * ty + qz * tx - qx * tz,
      z + qw * tz + qx * ty - qy * tx,
    ];
    p.forEach((v, i) => {
      min[i] = Math.min(min[i], v + placement.positionMeters[i]);
      max[i] = Math.max(max[i], v + placement.positionMeters[i]);
    });
  }
  return { min, max };
}

/** Admission only: never migrates existing layouts. Shared by UI and atomic commits. */
export function placementAvailability(
  s: ClosetSnapshot,
  subject: Subject,
  group: SemanticGroup,
  slot: number,
): { available: boolean; reason: string } {
  if (group === "unplaced") return { available: true, reason: "" };
  let placement: Placement;
  try {
    placement = makePlacement("candidate", s.roomId, group, slot, "candidate");
  } catch {
    return {
      available: false,
      reason: "That destination no longer exists. Choose another slot.",
    };
  }
  const neighbors = s.items.filter(
    (i) => i.id !== subject.id && i.placement.semanticGroup === group,
  );
  if (neighbors.some((i) => i.placement.slotId === slot))
    return {
      available: false,
      reason: "That slot is occupied. Choose an empty slot.",
    };
  if (group === "shelf.shoes") {
    const candidate = worldBounds(subject, placement);
    for (const item of neighbors) {
      const other = worldBounds(item, item.placement);
      // Horizontal footprint clearance also handles photo billboards with zero depth.
      if (
        [0, 2].every(
          (i) =>
            candidate.min[i] < other.max[i] + 0.01 &&
            candidate.max[i] > other.min[i] - 0.01,
        )
      )
        return {
          available: false,
          reason:
            "Not enough space beside this pair. Choose a farther slot or the Unplaced tray.",
        };
    }
  }
  return { available: true, reason: "" };
}

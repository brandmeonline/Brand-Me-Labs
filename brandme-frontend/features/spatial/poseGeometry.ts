import type { OverlayAnchor } from "./cameraSession";
export type Landmark = { x: number; y: number; visibility?: number };
/** Approximate 2D alignment only. Never produces measurements or fit assertions. */
export function poseAnchor(
  points: Landmark[],
  width: number,
  height: number,
): OverlayAnchor | null {
  const [l, r, hl, hr] = [points[11], points[12], points[23], points[24]];
  if (
    ![l, r, hl, hr].every(
      (p) =>
        p &&
        Number.isFinite(p.x) &&
        Number.isFinite(p.y) &&
        p.x >= 0 &&
        p.x <= 1 &&
        p.y >= 0 &&
        p.y <= 1 &&
        (p.visibility ?? 0) >= 0.65,
    )
  )
    return null;
  const shoulders = [l, r].sort((a, b) => a.x - b.x);
  const w = Math.hypot((l.x - r.x) * width, (l.y - r.y) * height) / width;
  const h = (hl.y + hr.y - l.y - r.y) / 2;
  if (w < 0.08 || h < 0.1 || !width || !height) return null;
  return {
    x: 1 - (l.x + r.x) / 2,
    y: (l.y + r.y) / 2 - h * 0.12,
    width: Math.min(0.8, w * 1.7),
    height: Math.min(0.85, h * 1.15),
    angle: Math.max(
      -0.45,
      Math.min(
        0.45,
        -Math.atan2(
          (shoulders[1].y - shoulders[0].y) * height,
          (shoulders[1].x - shoulders[0].x) * width,
        ),
      ),
    ),
  };
}

import type { Room, Vector3 } from "./types";

export interface CameraPose {
  position: Vector3;
  target: Vector3;
}
export interface SavedCamera extends CameraPose {
  id: string;
  name: string;
}
const key = (room: string) => `brandme.spatial.camera.v1:${room}`;
export function validCamera(value: unknown): value is CameraPose {
  const p = value as CameraPose | undefined;
  return (
    !!p &&
    [p.position, p.target].every(
      (v) =>
        Array.isArray(v) &&
        v.length === 3 &&
        v.every((n) => Number.isFinite(n) && Math.abs(n) < 40),
    )
  );
}
type Preferences = {
  version: 1;
  last?: CameraPose & { view: string };
  saved: SavedCamera[];
};
function read(room: string): Preferences {
  try {
    const p = JSON.parse(localStorage.getItem(key(room)) || "null");
    if (p?.version === 1)
      return {
        version: 1,
        last:
          validCamera(p.last) && typeof p.last.view === "string"
            ? p.last
            : undefined,
        saved: Array.isArray(p.saved)
          ? p.saved
              .filter(
                (v: SavedCamera) =>
                  validCamera(v) &&
                  typeof v.id === "string" &&
                  typeof v.name === "string" &&
                  v.name.length <= 48,
              )
              .slice(0, 8)
          : [],
      };
  } catch {
    /* Storage restrictions never make the scene unusable. */
  }
  return { version: 1, saved: [] };
}
function write(room: string, p: Preferences) {
  localStorage.setItem(key(room), JSON.stringify(p));
}
export function restoreCamera(room: string, view: string) {
  const p = read(room);
  return p.last?.view === view ? p.last : undefined;
}
export function persistCamera(room: string, view: string, pose: CameraPose) {
  if (!validCamera(pose)) return;
  try {
    write(room, { ...read(room), last: { ...pose, view } });
  } catch {
    /* Best effort, device-local only. */
  }
}
export function savedCameras(room: string) {
  return read(room).saved;
}
export function saveCamera(room: string, name: string, pose: CameraPose) {
  if (!name.trim() || !validCamera(pose))
    throw new Error("Name this view and open a 3D room first.");
  const p = read(room);
  if (p.saved.length >= 8)
    throw new Error(
      "Remove a saved view before adding another (eight per room).",
    );
  p.saved.push({
    ...pose,
    id: crypto.randomUUID(),
    name: name.trim().slice(0, 48),
  });
  write(room, p);
  return p.saved;
}
export function removeCamera(room: string, id: string) {
  const p = read(room);
  p.saved = p.saved.filter((v) => v.id !== id);
  write(room, p);
  return p.saved;
}

/** Project against the exact fixed add-room camera without eagerly importing Three. */
export function projectRoomPoint(room: Room, point: Vector3, aspect: number) {
  const sub = (a: Vector3, b: Vector3): Vector3 =>
    a.map((v, i) => v - b[i]) as Vector3;
  const norm = (v: Vector3): Vector3 => {
    const n = Math.hypot(...v);
    return v.map((x) => x / n) as Vector3;
  };
  const cross = (a: Vector3, b: Vector3): Vector3 => [
    a[1] * b[2] - a[2] * b[1],
    a[2] * b[0] - a[0] * b[2],
    a[0] * b[1] - a[1] * b[0],
  ];
  const dot = (a: Vector3, b: Vector3) =>
    a.reduce((sum, x, i) => sum + x * b[i], 0);
  const forward = norm(sub(room.camera.target, room.camera.position)),
    right = norm(cross(forward, [0, 1, 0])),
    up = cross(right, forward);
  const relative = sub(point, room.camera.position),
    depth = Math.max(0.05, dot(relative, forward));
  const scale = Math.tan((room.camera.fov * Math.PI) / 360) * depth;
  return {
    x: 0.5 + dot(relative, right) / (2 * scale * aspect),
    y: 0.5 - dot(relative, up) / (2 * scale),
  };
}

import catalog from "./generated-catalog.json";
import type { Asset, Room, SemanticGroup, Placement, Vector3 } from "./types";
export const rooms = catalog.rooms as unknown as Room[];
export const assets = catalog.products as unknown as Asset[];
export const photoOnly: Asset = {
  id: "photo-only",
  slug: "photo-only",
  title: "My reference overshirt",
  category: "top",
  revision: "original-v1",
  fidelity: "P0",
  fidelityLabel: "Photo display",
  poster: "/demo/photo-only/poster.webp",
  rights: "/demo/rights.json",
};
export const allAssets = [...assets, photoOnly];
export function roomById(id: string): Room {
  const room = rooms.find((r) => r.id === id);
  if (!room) throw new Error("This room is unavailable.");
  return room;
}
export function defaultGroup(category: string): SemanticGroup {
  return category === "shoes"
    ? "shelf.shoes"
    : category === "accessory"
      ? "tray.accessories"
      : "rail.left";
}
export function eligibleGroups(category: string, room: Room) {
  const ids: SemanticGroup[] =
    category === "shoes"
      ? ["shelf.shoes"]
      : category === "accessory"
        ? ["tray.accessories"]
        : ["rail.left", "rail.right", "shelf.folded", "stand.outfit"];
  return room.groups.filter((g) => ids.includes(g.id));
}
export function positionFor(
  room: Room,
  group: SemanticGroup,
  slotId: number,
): Vector3 {
  if (group === "unplaced") return [0, 0, 0];
  const anchor = room.groups.find((g) => g.id === group);
  if (
    !anchor ||
    !Number.isInteger(slotId) ||
    slotId < 0 ||
    slotId >= anchor.capacity
  )
    throw new Error("That destination no longer exists. Choose another slot.");
  const x =
    anchor.center[0] +
    (slotId - (anchor.capacity - 1) / 2) *
      (group.startsWith("rail.")
        ? anchor.pitch
        : anchor.width / anchor.capacity);
  return [x, anchor.center[1], anchor.center[2]];
}
export function makePlacement(
  itemId: string,
  roomId: string,
  group: SemanticGroup,
  slot: number,
  revision: string,
  version = 1,
): Placement {
  const yaw = group.startsWith("rail.") ? 0.38 : 0;
  return {
    wardrobeItemId: itemId,
    roomId,
    semanticGroup: group,
    slotId: slot,
    positionMeters: positionFor(roomById(roomId), group, slot),
    rotationQuaternion: [0, Math.sin(yaw / 2), 0, Math.cos(yaw / 2)],
    uniformScale: 1,
    assetRevision: revision,
    version,
  };
}

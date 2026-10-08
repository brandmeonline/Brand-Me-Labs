export type Fidelity = "P0" | "P1" | "P2" | "P3" | "P4";
export const fidelityLabels: Record<Fidelity, string> = {
  P0: "Photo display",
  P1: "Approximate 3D",
  P2: "Product 3D model",
  P3: "Live visual preview",
  P4: "Fit estimate with method and limits",
};
export type Vector3 = [number, number, number];
export type SemanticGroup =
  | "rail.left"
  | "rail.right"
  | "shelf.shoes"
  | "shelf.folded"
  | "tray.accessories"
  | "stand.outfit"
  | "unplaced";
export interface Asset {
  id: string;
  slug: string;
  title: string;
  category: string;
  revision: string;
  fidelity: Fidelity;
  fidelityLabel: string;
  glb?: string;
  lowGlb?: string;
  usdz?: string;
  poster: string;
  rights: string;
  displayScaleBounds?: number[];
  dimensionsMeters?: number[];
  pivot?: string;
  triangleCount?: number;
  drawCalls?: number;
}
export interface Room {
  id: string;
  title: string;
  glb: string;
  poster: string;
  lightKelvin: number;
  groups: {
    id: SemanticGroup;
    center: Vector3;
    capacity: number;
    pitch: number;
    width: number;
  }[];
  camera: {
    fov: number;
    near: number;
    far: number;
    position: Vector3;
    target: Vector3;
  };
  views: { id: string; name: string; position: Vector3; target: Vector3 }[];
}
export type ItemStatus =
  | "owned"
  | "want"
  | "on_the_way"
  | "digital"
  | "archive";
export interface Placement {
  wardrobeItemId: string;
  roomId: string;
  semanticGroup: SemanticGroup;
  slotId: number;
  positionMeters: Vector3;
  rotationQuaternion: [number, number, number, number];
  uniformScale: number;
  assetRevision: string;
  version: number;
}
export interface ClosetItem {
  id: string;
  productId: string | null;
  title: string;
  category: string;
  status: ItemStatus;
  posterUrl: string;
  fidelity: Fidelity;
  assetSlug: string | null;
  version: number;
  source: "fictional_catalog" | "self_declared";
  notes: string;
  placement: Placement;
}
export interface WardrobeCapsule {
  id: string;
  title: string;
  itemIds: string[];
}
export interface ClosetSnapshot {
  capsules?: WardrobeCapsule[];
  version: number;
  roomId: string;
  items: ClosetItem[];
  reducedMotion: boolean;
  simpleView: boolean;
  namedView: string;
}
export const groupLabels: Record<SemanticGroup, string> = {
  "rail.left": "Work rail",
  "rail.right": "Occasion rail",
  "shelf.shoes": "Shoe shelf",
  "shelf.folded": "Folded shelf",
  "tray.accessories": "Accessory tray",
  "stand.outfit": "Outfit stand",
  unplaced: "Unplaced tray",
};
export const statusLabels: Record<ItemStatus, string> = {
  owned: "Owned",
  want: "Want",
  on_the_way: "On the way",
  digital: "Digital",
  archive: "Archive",
};

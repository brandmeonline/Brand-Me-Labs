import {
  allAssets,
  defaultGroup,
  eligibleGroups,
  makePlacement,
  roomById,
} from "../spatial/catalog";
import type {
  ClosetItem,
  ClosetSnapshot,
  ItemStatus,
  SemanticGroup,
} from "../spatial/types";
export type AddInput = {
  productId: string | null;
  title: string;
  category: string;
  status: ItemStatus;
  posterUrl: string;
  assetSlug: string | null;
  group: SemanticGroup;
  slot: number;
};
export type ClosetCommand =
  | { type: "add"; input: AddInput }
  | { type: "undo_add"; itemId: string; expectedItemVersion: number }
  | {
      type: "move";
      itemId: string;
      expectedItemVersion: number;
      group: SemanticGroup;
      slot: number;
    }
  | { type: "theme"; roomId: string }
  | {
      type: "preferences";
      reducedMotion?: boolean;
      simpleView?: boolean;
      namedView?: string;
    }
  | {
      type: "notes";
      itemId: string;
      expectedItemVersion: number;
      notes: string;
    };
export interface ClosetRepository {
  readonly persistenceLabel: string;
  read(): Promise<ClosetSnapshot>;
  commit(
    command: ClosetCommand,
    expectedVersion: number,
    operationId: string,
  ): Promise<{ snapshot: ClosetSnapshot; itemId?: string }>;
  subscribe(listener: () => void): () => void;
}
export class ClosetConflict extends Error {
  constructor(public current: ClosetSnapshot) {
    super(
      "Your closet changed in another window. The saved version is shown; review and try again.",
    );
  }
}
type RecordState = {
  snapshot: ClosetSnapshot;
  operations: Record<string, { digest: string; itemId?: string }>;
};
const clone = <T>(x: T): T => structuredClone(x);
export function initialSnapshot(): ClosetSnapshot {
  const roomId = "walnut_atelier";
  const starts: Record<string, [SemanticGroup, number]> = {
    overshirt: ["rail.left", 2],
    tee: ["rail.left", 6],
    jacket: ["rail.left", 10],
    dress: ["rail.right", 3],
    trousers: ["rail.right", 8],
    sneaker: ["shelf.shoes", 4],
    bag: ["tray.accessories", 3],
  };
  return {
    version: 1,
    roomId,
    reducedMotion: false,
    simpleView: false,
    namedView: "room",
    items: allAssets
      .filter((a) => starts[a.slug])
      .map((a) => {
        const id = `guest-${a.slug}`,
          [group, slot] = starts[a.slug];
        return {
          id,
          productId: a.id,
          title: a.title,
          category: a.category,
          status: "owned",
          posterUrl: a.poster,
          fidelity: a.fidelity,
          assetSlug: a.slug,
          source: "fictional_catalog",
          notes: "",
          version: 1,
          placement: makePlacement(id, roomId, group, slot, a.revision),
        };
      }),
  };
}
function freeSlot(
  s: ClosetSnapshot,
  group: SemanticGroup,
  slot: number,
  except?: string,
) {
  if (group === "unplaced") return;
  const room = roomById(s.roomId);
  makePlacement("check", s.roomId, group, slot, "check");
  if (
    s.items.some(
      (i) =>
        i.id !== except &&
        i.placement.semanticGroup === group &&
        i.placement.slotId === slot,
    )
  )
    throw new Error("That slot is occupied. Choose an empty slot.");
  return room;
}
function apply(
  snapshot: ClosetSnapshot,
  command: ClosetCommand,
): { snapshot: ClosetSnapshot; itemId?: string } {
  const s = clone(snapshot);
  let itemId: string | undefined;
  if (command.type === "add") {
    const x = command.input,
      a = allAssets.find((a) => a.slug === x.assetSlug);
    if (!x.title.trim() || x.title.length > 120)
      throw new Error("Use an item name between 1 and 120 characters.");
    if (
      !["owned", "want", "on_the_way", "digital", "archive"].includes(x.status)
    )
      throw new Error("Choose a valid closet status.");
    if (x.assetSlug && !a)
      throw new Error("This garment asset is unavailable.");
    if (
      x.group !== "unplaced" &&
      !eligibleGroups(x.category, roomById(s.roomId)).some(
        (g) => g.id === x.group,
      )
    )
      throw new Error("Choose a suitable destination for this category.");
    if (
      !x.posterUrl.startsWith("/demo/") &&
      !/^data:image\/(png|webp|jpeg);base64,/.test(x.posterUrl)
    )
      throw new Error("Use an approved image or a local photo.");
    freeSlot(s, x.group, x.slot);
    itemId = crypto.randomUUID();
    s.items.push({
      id: itemId,
      productId: a?.id ?? null,
      title: x.title.trim(),
      category: x.category,
      status: x.status,
      posterUrl: a?.poster ?? x.posterUrl,
      assetSlug: a?.slug ?? null,
      fidelity: a?.fidelity ?? "P0",
      source: a ? "fictional_catalog" : "self_declared",
      notes: "",
      version: 1,
      placement: makePlacement(
        itemId,
        s.roomId,
        x.group,
        x.slot,
        a?.revision ?? "photo-v1",
      ),
    });
  } else if (command.type === "theme") {
    const room = roomById(command.roomId);
    s.roomId = room.id;
    s.namedView = "room";
    const occupied = new Set<string>();
    s.items = s.items.map((item) => {
      let group = item.placement.semanticGroup;
      const anchor = room.groups.find((a) => a.id === group);
      const slot = item.placement.slotId,
        key = `${group}:${slot}`;
      if (!anchor || slot >= anchor.capacity || occupied.has(key))
        group = "unplaced";
      else occupied.add(key);
      return {
        ...item,
        version: item.version + 1,
        placement: makePlacement(
          item.id,
          room.id,
          group,
          group === "unplaced" ? 0 : slot,
          item.placement.assetRevision,
          item.placement.version + 1,
        ),
      };
    });
  } else if (command.type === "preferences") {
    if (typeof command.reducedMotion === "boolean")
      s.reducedMotion = command.reducedMotion;
    if (typeof command.simpleView === "boolean")
      s.simpleView = command.simpleView;
    if (command.namedView) {
      if (!roomById(s.roomId).views.some((v) => v.id === command.namedView))
        throw new Error("Unknown camera view.");
      s.namedView = command.namedView;
    }
  } else {
    const item = s.items.find((i) => i.id === command.itemId);
    if (!item || item.version !== command.expectedItemVersion)
      throw new ClosetConflict(snapshot);
    if (command.type === "undo_add")
      s.items = s.items.filter((i) => i.id !== item.id);
    if (command.type === "notes") {
      item.notes = command.notes.slice(0, 2000);
      item.version++;
    }
    if (command.type === "move") {
      if (
        command.group !== "unplaced" &&
        !eligibleGroups(item.category, roomById(s.roomId)).some(
          (g) => g.id === command.group,
        )
      )
        throw new Error("Choose a suitable destination.");
      freeSlot(s, command.group, command.slot, item.id);
      item.placement = makePlacement(
        item.id,
        s.roomId,
        command.group,
        command.slot,
        item.placement.assetRevision,
        item.placement.version + 1,
      );
      item.version++;
    }
  }
  s.version++;
  return { snapshot: s, itemId };
}
/** Guest demo only. IndexedDB transactions serialize version checks and commits across tabs.
 * A production host must inject an authenticated API implementation of ClosetRepository. */
export function createGuestClosetRepository(
  namespace = "brandme.spatial.guest.v1",
): ClosetRepository {
  let dbPromise: Promise<IDBDatabase> | undefined;
  const listeners = new Set<() => void>();
  let channel: BroadcastChannel | undefined;
  function db() {
    if (!dbPromise)
      dbPromise = new Promise((resolve, reject) => {
        if (!globalThis.indexedDB) {
          reject(
            new Error(
              "Device storage is unavailable. Enable it to save your closet.",
            ),
          );
          return;
        }
        const request = indexedDB.open(namespace, 1);
        request.onupgradeneeded = () =>
          request.result.createObjectStore("closet");
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error);
      });
    return dbPromise;
  }
  function announce() {
    listeners.forEach((f) => f());
    channel?.postMessage("changed");
  }
  return {
    persistenceLabel: "Guest demo · Saved on this device",
    async read() {
      const database = await db();
      return new Promise((resolve, reject) => {
        const tx = database.transaction("closet", "readwrite"),
          store = tx.objectStore("closet"),
          get = store.get("state");
        let state: RecordState;
        get.onsuccess = () => {
          state = get.result ?? { snapshot: initialSnapshot(), operations: {} };
          if (!get.result) store.put(state, "state");
        };
        tx.oncomplete = () => resolve(clone(state.snapshot));
        tx.onerror = () => reject(tx.error);
        tx.onabort = () =>
          reject(tx.error ?? new Error("Storage was interrupted."));
      });
    },
    async commit(command, expectedVersion, operationId) {
      if (!operationId) throw new Error("Missing operation id.");
      const database = await db();
      return new Promise((resolve, reject) => {
        const tx = database.transaction("closet", "readwrite"),
          store = tx.objectStore("closet"),
          get = store.get("state");
        let result: { snapshot: ClosetSnapshot; itemId?: string },
          error: unknown;
        get.onsuccess = () => {
          try {
            const state: RecordState = get.result ?? {
              snapshot: initialSnapshot(),
              operations: {},
            };
            const digest = JSON.stringify(command),
              previous = state.operations[operationId];
            if (previous) {
              if (previous.digest !== digest)
                throw new Error(
                  "This operation id was already used for a different change.",
                );
              result = { snapshot: state.snapshot, itemId: previous.itemId };
              return;
            }
            if (state.snapshot.version !== expectedVersion)
              throw new ClosetConflict(state.snapshot);
            result = apply(state.snapshot, command);
            state.snapshot = result.snapshot;
            state.operations[operationId] = { digest, itemId: result.itemId };
            store.put(state, "state");
          } catch (e) {
            error = e;
            tx.abort();
          }
        };
        tx.oncomplete = () => {
          announce();
          resolve(clone(result));
        };
        tx.onerror = () => reject(tx.error);
        tx.onabort = () =>
          reject(error ?? tx.error ?? new Error("Unable to save. Try again."));
      });
    },
    subscribe(listener) {
      listeners.add(listener);
      if (!channel && typeof BroadcastChannel !== "undefined") {
        channel = new BroadcastChannel(namespace);
        channel.onmessage = () => listeners.forEach((f) => f());
      }
      return () => {
        listeners.delete(listener);
        if (!listeners.size) {
          channel?.close();
          channel = undefined;
        }
      };
    },
  };
}

"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { useCloset } from "./useCloset";
import {
  allAssets,
  defaultGroup,
  eligibleGroups,
  roomById,
} from "../spatial/catalog";
import { RoomViewport } from "../spatial/RoomViewport";
import {
  SignaturePlacement,
  type PlacementFlight,
} from "../spatial/SignaturePlacement";
import { useMotionPreference } from "../spatial/useMotionPreference";
import {
  fidelityLabels,
  groupLabels,
  type ItemStatus,
  type SemanticGroup,
} from "../spatial/types";
import type { AddInput } from "./repository";
import styles from "../spatial/spatial.module.css";
export default function AddItemPage() {
  const { snapshot, error, setError, commit, persistenceLabel } = useCloset(),
    [mode, setMode] = useState<"catalog" | "manual">("catalog"),
    [assetSlug, setAssetSlug] = useState("overshirt"),
    [title, setTitle] = useState(""),
    [category, setCategory] = useState("top"),
    [status, setStatus] = useState<ItemStatus>("want"),
    [group, setGroup] = useState<SemanticGroup>("rail.left"),
    [slot, setSlot] = useState(0),
    [photo, setPhoto] = useState("/demo/photo-only/poster.webp"),
    [duplicateConfirmed, setDuplicateConfirmed] = useState(false),
    [pending, setPending] = useState(false),
    [message, setMessage] = useState(""),
    [flight, setFlight] = useState<PlacementFlight>(),
    [undo, setUndo] = useState<{
      id: string;
      version: number;
      expires: number;
    }>(),
    [fallback, setFallback] = useState("");
  const operation = useRef<{ id: string; input: string } | undefined>(
      undefined,
    ),
    source = useRef<HTMLImageElement>(null),
    destination = useRef<HTMLDivElement>(null),
    mounted = useRef(true),
    reduced = useMotionPreference(snapshot?.reducedMotion);
  const asset = allAssets.find((a) => a.slug === assetSlug)!,
    actualCategory = mode === "catalog" ? asset.category : category;
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  useEffect(() => {
    if (!snapshot) return;
    const room = roomById(snapshot.roomId),
      desired = defaultGroup(actualCategory),
      target =
        room.groups.find((g) => g.id === desired) ??
        eligibleGroups(actualCategory, room)[0];
    const free = target
      ? Array.from({ length: target.capacity }, (_, i) => i).find(
          (slot) =>
            !snapshot.items.some(
              (x) =>
                x.placement.semanticGroup === target.id &&
                x.placement.slotId === slot,
            ),
        )
      : undefined;
    setGroup(free === undefined ? "unplaced" : target!.id);
    setSlot(free ?? 0);
    setDuplicateConfirmed(false);
  }, [assetSlug, actualCategory, snapshot?.roomId, mode]);
  useEffect(() => {
    if (!undo) return;
    const timer = setTimeout(
      () => setUndo(undefined),
      Math.max(0, undo.expires - Date.now()),
    );
    return () => clearTimeout(timer);
  }, [undo]);
  const finishFlight = useCallback(() => setFlight(undefined), []);
  if (!snapshot)
    return (
      <section className={styles.root}>
        <h1>Add a piece</h1>
        <p role="status">{error || "Opening your closet…"}</p>
      </section>
    );
  const room = roomById(snapshot.roomId),
    duplicate =
      mode === "catalog" &&
      snapshot.items.some((i) => i.productId === asset.id),
    poster = mode === "catalog" ? asset.poster : photo;
  async function readPhoto(file?: File) {
    if (!file) return;
    if (
      !["image/jpeg", "image/png", "image/webp"].includes(file.type) ||
      file.size > 8 * 1024 * 1024
    ) {
      setError("Choose a JPEG, PNG, or WebP under 8 MB.");
      return;
    }
    try {
      const bitmap = await createImageBitmap(file);
      if (bitmap.width * bitmap.height > 40_000_000) {
        bitmap.close();
        throw new Error("Use an image under 40 megapixels.");
      }
      const canvas = document.createElement("canvas"),
        scale = Math.min(1, 1000 / Math.max(bitmap.width, bitmap.height));
      canvas.width = bitmap.width * scale;
      canvas.height = bitmap.height * scale;
      canvas
        .getContext("2d")!
        .drawImage(bitmap, 0, 0, canvas.width, canvas.height);
      bitmap.close();
      setPhoto(canvas.toDataURL("image/webp", 0.88));
      setMessage("Photo prepared on this device. No upload was sent.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not read that image.");
    }
  }
  async function add() {
    if (pending) return;
    const input: AddInput = {
      productId: mode === "catalog" ? asset.id : null,
      title: mode === "catalog" ? asset.title : title,
      category: actualCategory,
      status,
      posterUrl: poster,
      assetSlug: mode === "catalog" ? asset.slug : null,
      group,
      slot,
    };
    const digest = JSON.stringify(input);
    if (!operation.current || operation.current.input !== digest)
      operation.current = { id: crypto.randomUUID(), input: digest };
    setPending(true);
    setMessage("Saving your item and destination…");
    const from = source.current?.getBoundingClientRect(),
      to = destination.current?.getBoundingClientRect();
    try {
      const result = await commit({ type: "add", input }, operation.current.id);
      if (!mounted.current) return;
      const item = result.snapshot.items.find((i) => i.id === result.itemId);
      if (!item)
        throw new Error("Saved item could not be found. Reload your closet.");
      setUndo({
        id: item.id,
        version: item.version,
        expires: Date.now() + 10000,
      });
      setMessage(`Added to your ${groupLabels[group]}.`);
      if (from && to && !document.hidden && !reduced && group !== "unplaced")
        setFlight({
          itemId: item.id,
          poster,
          source: { x: from.x + from.width / 2, y: from.y + from.height / 2 },
          destination: {
            x: to.x + to.width * (0.5 + item.placement.positionMeters[0] / 5.7),
            y: to.y + to.height * 0.48,
          },
        });
      operation.current = undefined;
    } catch {
      if (mounted.current)
        setMessage(
          "Your item was not settled. Review the error and retry the same request.",
        );
    } finally {
      if (mounted.current) setPending(false);
    }
  }
  async function undoAdd() {
    if (!undo || Date.now() > undo.expires) return;
    try {
      await commit({
        type: "undo_add",
        itemId: undo.id,
        expectedItemVersion: undo.version,
      });
      setUndo(undefined);
      setFlight(undefined);
      setMessage("Addition undone. The item and placement were removed.");
    } catch {}
  }
  return (
    <section className={styles.root}>
      <header className={styles.header}>
        <div>
          <p className={styles.eyebrow}>Make it yours</p>
          <h1>A new place in your wardrobe.</h1>
          <p className={styles.muted}>{persistenceLabel}</p>
        </div>
        <a className={styles.button} href="/closet">
          Back to closet
        </a>
      </header>
      <div className={styles.toolbar}>
        <button
          aria-pressed={mode === "catalog"}
          onClick={() => setMode("catalog")}
        >
          Fictional catalog
        </button>
        <button
          aria-pressed={mode === "manual"}
          onClick={() => {
            setMode("manual");
            setStatus("owned");
          }}
        >
          Manual / local photo
        </button>
      </div>
      {error && (
        <p role="alert" className={`${styles.notice} ${styles.error}`}>
          {error}
        </p>
      )}
      <div className={styles.divider} />
      <div className={styles.workspace}>
        <div className={styles.stack}>
          {mode === "catalog" ? (
            <div className={styles.catalog}>
              {allAssets.map((a) => (
                <button
                  key={a.id}
                  className={`${styles.assetCard} ${assetSlug === a.slug ? styles.selected : ""}`}
                  aria-pressed={assetSlug === a.slug}
                  onClick={() => setAssetSlug(a.slug)}
                >
                  <img
                    src={a.poster}
                    alt=""
                    width="180"
                    height="220"
                    loading="lazy"
                  />
                  <strong>{a.title}</strong>
                  <span className={styles.fidelity}>
                    {fidelityLabels[a.fidelity]}
                  </span>
                </button>
              ))}
            </div>
          ) : (
            <div className={styles.card}>
              <label>
                Item name
                <input
                  value={title}
                  maxLength={120}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="My linen shirt"
                />
              </label>
              <label>
                Category
                <select
                  value={category}
                  onChange={(e) => setCategory(e.target.value)}
                >
                  <option value="top">Top</option>
                  <option value="bottom">Bottom</option>
                  <option value="dress">Dress</option>
                  <option value="outerwear">Outerwear</option>
                  <option value="shoes">Shoes</option>
                  <option value="accessory">Accessory</option>
                </select>
              </label>
              <label>
                Optional photo
                <input
                  type="file"
                  accept="image/jpeg,image/png,image/webp"
                  onChange={(e) => void readPhoto(e.target.files?.[0])}
                />
              </label>
              <p className={styles.muted}>
                Prepared and saved on this device. We do not send your photo,
                infer a size, or claim verified ownership. Without a photo, a
                clearly labeled reference image is used.
              </p>
            </div>
          )}
          <div ref={destination}>
            <RoomViewport
              room={room}
              items={snapshot.items.filter((i) => i.id !== flight?.itemId)}
              onSelect={() => {}}
              onFallback={setFallback}
              namedView="room"
              reducedMotion={reduced}
              simpleView={snapshot.simpleView || !!fallback}
            />
          </div>
        </div>
        <aside className={styles.inspector}>
          <img
            ref={source}
            src={poster}
            width="240"
            height="200"
            alt={
              mode === "catalog" ? asset.title : title || "Local item reference"
            }
          />
          <div className={styles.stack}>
            <span className={styles.fidelity}>
              {mode === "catalog"
                ? fidelityLabels[asset.fidelity]
                : "Photo display"}
            </span>
            <h2>{mode === "catalog" ? asset.title : title || "Your piece"}</h2>
          </div>
          <div className={styles.field}>
            <label>
              Closet status
              <select
                value={status}
                onChange={(e) => setStatus(e.target.value as ItemStatus)}
              >
                <option value="want">Want · save an aspiration</option>
                <option value="owned">Owned · I declare I own this</option>
                <option value="on_the_way">On the way · self-reported</option>
                <option value="digital">Digital</option>
              </select>
            </label>
            <label>
              Destination
              <select
                value={group}
                onChange={(e) => {
                  setGroup(e.target.value as SemanticGroup);
                  setSlot(0);
                }}
              >
                {eligibleGroups(actualCategory, room).map((g) => (
                  <option key={g.id} value={g.id}>
                    {groupLabels[g.id]}
                  </option>
                ))}
                <option value="unplaced">Unplaced tray</option>
              </select>
            </label>
            <label>
              Slot
              <select
                value={slot}
                onChange={(e) => setSlot(Number(e.target.value))}
              >
                {Array.from(
                  {
                    length:
                      room.groups.find((g) => g.id === group)?.capacity ?? 1,
                  },
                  (_, i) => (
                    <option key={i} value={i}>
                      {i + 1}
                      {snapshot.items.some(
                        (x) =>
                          x.placement.semanticGroup === group &&
                          x.placement.slotId === i,
                      )
                        ? " · occupied"
                        : ""}
                    </option>
                  ),
                )}
              </select>
            </label>
            {duplicate && (
              <label className={styles.checkbox}>
                <input
                  type="checkbox"
                  checked={duplicateConfirmed}
                  onChange={(e) => setDuplicateConfirmed(e.target.checked)}
                />
                This is a separate item. Keep both records.
              </label>
            )}
            <button
              className={styles.primary}
              disabled={
                pending ||
                (mode === "manual" && !title.trim()) ||
                (duplicate && !duplicateConfirmed)
              }
              onClick={() => void add()}
            >
              {pending ? "Saving…" : "Add to closet"}
            </button>
            <p className={styles.muted}>
              Catalog discoveries start in Want. A closet status does not
              establish authenticity or a digital entitlement.
            </p>
          </div>
        </aside>
      </div>
      <p role="status" className={styles.notice}>
        {message || "Review your item, status, and destination before adding."}
      </p>
      {flight && (
        <SignaturePlacement
          flight={flight}
          reducedMotion={reduced}
          onDone={finishFlight}
        />
      )}
      {undo && (
        <div className={styles.toast}>
          <span>Item added</span>
          <button onClick={() => void undoAdd()}>Undo</button>
        </div>
      )}
    </section>
  );
}

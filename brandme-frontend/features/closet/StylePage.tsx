"use client";
import { useEffect, useState } from "react";
import { useCloset } from "./useCloset";
import { OutfitEditor, type OutfitComposition } from "../spatial/OutfitEditor";
import { useMotionPreference } from "../spatial/useMotionPreference";
import styles from "../spatial/spatial.module.css";
const seed: OutfitComposition = {
  title: "A quieter kind of statement",
  occasion: "Everyday",
  notes: "",
  itemIds: [],
};
type SavedLook = {
  id: string;
  version: number;
  composition: OutfitComposition;
};
async function db() {
  return new Promise<IDBDatabase>((resolve, reject) => {
    const r = indexedDB.open("brandme.spatial.guest-outfits.v1", 1);
    r.onupgradeneeded = () =>
      r.result.createObjectStore("outfits", { keyPath: "id" });
    r.onsuccess = () => resolve(r.result);
    r.onerror = () => reject(r.error);
  });
}
export default function StylePage({
  outfitId = "current",
}: {
  outfitId?: string;
}) {
  const { snapshot, error } = useCloset(),
    [value, setValue] = useState<OutfitComposition>(seed),
    [version, setVersion] = useState(0),
    [loaded, setLoaded] = useState(false),
    [loadError, setLoadError] = useState("");
  const reduced = useMotionPreference(snapshot?.reducedMotion);
  useEffect(() => {
    let live = true;
    void db()
      .then((database) => {
        const tx = database.transaction("outfits"),
          request = tx.objectStore("outfits").get(outfitId);
        request.onsuccess = () => {
          if (live) {
            const saved = request.result as SavedLook | undefined;
            if (saved) {
              setValue(saved.composition);
              setVersion(saved.version);
            }
            setLoaded(true);
          }
        };
        tx.onerror = () => {
          if (live) setLoadError("Your saved look could not be read.");
        };
        tx.oncomplete = () => database.close();
      })
      .catch(() => setLoadError("Device storage is unavailable."));
    return () => {
      live = false;
    };
  }, [outfitId]);
  async function save(composition: OutfitComposition) {
    if (!snapshot) throw new Error("Your closet is still loading.");
    if (
      composition.itemIds.some((id) => !snapshot.items.some((i) => i.id === id))
    )
      throw new Error("Remove unavailable items before saving.");
    const database = await db();
    await new Promise<void>((resolve, reject) => {
      const tx = database.transaction("outfits", "readwrite"),
        store = tx.objectStore("outfits"),
        request = store.get(outfitId);
      let conflict = false;
      request.onsuccess = () => {
        const old = request.result as SavedLook | undefined;
        if ((old?.version ?? 0) !== version) {
          conflict = true;
          tx.abort();
          return;
        }
        store.put({ id: outfitId, version: version + 1, composition });
      };
      tx.oncomplete = () => {
        setVersion((v) => v + 1);
        database.close();
        resolve();
      };
      tx.onabort = () => {
        database.close();
        reject(
          new Error(
            conflict
              ? "This look changed in another window. Reload before saving."
              : "Your look could not be saved.",
          ),
        );
      };
      tx.onerror = () => reject(tx.error);
    });
  }
  return (
    <div className={styles.root}>
      <header className={styles.header}>
        <div>
          <p className={styles.eyebrow}>Style Me</p>
          <h1>Start with what is yours.</h1>
          <p className={styles.muted}>
            Guest look · Saved on this device · Original fictional starter items
          </p>
        </div>
        <a className={styles.button} href="/closet">
          My Closet
        </a>
      </header>
      {error || loadError ? (
        <p role="alert" className={styles.notice}>
          {error || loadError}
        </p>
      ) : !loaded || !snapshot ? (
        <p role="status">Opening your look…</p>
      ) : (
        <OutfitEditor
          items={snapshot.items}
          value={value}
          onChange={setValue}
          onSave={save}
          reducedMotion={reduced}
        />
      )}
    </div>
  );
}

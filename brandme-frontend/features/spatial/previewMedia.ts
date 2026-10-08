// Private browser-only guest media. Production provider jobs must use the authenticated media API.
const expiry = 24 * 60 * 60 * 1000;
type MediaRecord = {
  id: string;
  blob: Blob;
  createdAt: number;
  expiresAt: number | null;
  saved: boolean;
};
async function open() {
  return new Promise<IDBDatabase>((resolve, reject) => {
    const request = indexedDB.open("brandme.spatial.preview-media.v1", 1);
    request.onupgradeneeded = () =>
      request.result.createObjectStore("media", { keyPath: "id" });
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}
export async function storePreview(blob: Blob, now = Date.now()) {
  if (
    !["image/png", "image/webp", "image/jpeg"].includes(blob.type) ||
    blob.size > 8 * 1024 * 1024
  )
    throw new Error("Unsupported preview image.");
  const record: MediaRecord = {
    id: crypto.randomUUID(),
    blob,
    createdAt: now,
    expiresAt: now + expiry,
    saved: false,
  };
  const db = await open();
  try {
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction("media", "readwrite");
      tx.objectStore("media").add(record);
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
    return record.id;
  } finally {
    db.close();
  }
}
export async function readPreviews(now = Date.now()) {
  const db = await open();
  try {
    return await new Promise<MediaRecord[]>((resolve, reject) => {
      const tx = db.transaction("media", "readwrite"),
        store = tx.objectStore("media"),
        request = store.getAll();
      let kept: MediaRecord[] = [];
      request.onsuccess = () => {
        kept = request.result.filter(
          (r: MediaRecord) => r.saved || r.expiresAt! > now,
        );
        for (const r of request.result)
          if (!r.saved && r.expiresAt <= now) store.delete(r.id);
      };
      tx.oncomplete = () => resolve(kept);
      tx.onerror = () => reject(tx.error);
    });
  } finally {
    db.close();
  }
}
export async function deletePreview(id: string) {
  const db = await open();
  try {
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction("media", "readwrite");
      tx.objectStore("media").delete(id);
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
  } finally {
    db.close();
  }
}
export async function savePreview(id: string, now = Date.now()) {
  const db = await open();
  try {
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction("media", "readwrite"),
        store = tx.objectStore("media"),
        request = store.get(id);
      let expired = false;
      request.onsuccess = () => {
        const record = request.result as MediaRecord | undefined;
        if (!record || (!record.saved && record.expiresAt! <= now)) {
          expired = true;
          store.delete(id);
          return;
        }
        store.put({ ...record, saved: true, expiresAt: null });
      };
      tx.oncomplete = () =>
        expired
          ? reject(new Error("That preview expired. Capture a new one."))
          : resolve();
      tx.onerror = () => reject(tx.error);
    });
  } finally {
    db.close();
  }
}

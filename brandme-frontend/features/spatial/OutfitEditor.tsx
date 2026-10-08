"use client";
import { useState } from "react";
import { fidelityLabels, type Fidelity } from "./types";
import styles from "./spatial.module.css";
export type OutfitEditorItem = {
  id: string;
  title: string;
  category: string;
  posterUrl: string;
  fidelity: Fidelity;
};
export type OutfitComposition = {
  itemIds: string[];
  title: string;
  occasion: string;
  notes: string;
};
export type OutfitEditorProps = {
  items: readonly OutfitEditorItem[];
  value: OutfitComposition;
  onChange: (next: OutfitComposition) => void;
  onSave?: (next: OutfitComposition) => Promise<void>;
  readOnly?: boolean;
  reducedMotion?: boolean;
};
export function OutfitEditor({
  items,
  value,
  onChange,
  onSave,
  readOnly = false,
  reducedMotion = false,
}: OutfitEditorProps) {
  const [saving, setSaving] = useState(false),
    [message, setMessage] = useState("");
  const selected = value.itemIds.map((id) => items.find((i) => i.id === id));
  function move(index: number, offset: number) {
    const ids = [...value.itemIds],
      next = index + offset;
    if (next < 0 || next >= ids.length) return;
    [ids[index], ids[next]] = [ids[next], ids[index]];
    onChange({ ...value, itemIds: ids });
  }
  async function save() {
    if (!onSave || saving) return;
    setSaving(true);
    setMessage("Saving your look…");
    try {
      await onSave(value);
      setMessage("Look saved.");
    } catch (e) {
      setMessage(
        e instanceof Error
          ? e.message
          : "Your look could not be saved. Please retry.",
      );
    } finally {
      setSaving(false);
    }
  }
  return (
    <section
      className={styles.root}
      aria-label="Visual outfit editor"
      data-reduced-motion={reducedMotion}
    >
      <div className={styles.header}>
        <div>
          <p className={styles.eyebrow}>Style, on your terms</p>
          <h2>{value.title || "A look of your own"}</h2>
          <p className={styles.muted}>
            Arrange real closet items. Every representation shows its fidelity.
          </p>
        </div>
      </div>
      <div className={styles.outfit}>
        <div className={styles.composition} aria-label="Outfit composition">
          {!selected.length && (
            <p className={styles.muted}>Choose a piece to begin.</p>
          )}
          {selected.map((item, index) => (
            <figure key={value.itemIds[index]}>
              {item ? (
                <>
                  <img
                    src={item.posterUrl}
                    width="240"
                    height="300"
                    alt={item.title}
                  />
                  <figcaption>{item.title}</figcaption>
                  <span className={styles.fidelity}>
                    {fidelityLabels[item.fidelity]}
                  </span>
                </>
              ) : (
                <figcaption>Item unavailable · remove or replace it</figcaption>
              )}
            </figure>
          ))}
        </div>
        <div className={styles.stack}>
          <label>
            Look name
            <input
              disabled={readOnly || saving}
              maxLength={120}
              value={value.title}
              onChange={(e) => onChange({ ...value, title: e.target.value })}
            />
          </label>
          <label>
            Occasion
            <input
              disabled={readOnly || saving}
              maxLength={120}
              value={value.occasion}
              onChange={(e) => onChange({ ...value, occasion: e.target.value })}
            />
          </label>
          <label>
            Styling notes
            <textarea
              disabled={readOnly || saving}
              maxLength={2000}
              value={value.notes}
              onChange={(e) => onChange({ ...value, notes: e.target.value })}
            />
          </label>
          <div role="list" aria-label="Layer order">
            {value.itemIds.map((id, index) => (
              <div className={styles.outfitRow} role="listitem" key={id}>
                <span>
                  {index + 1}. {selected[index]?.title ?? "Unavailable item"}
                </span>
                {!readOnly && (
                  <>
                    <button
                      disabled={saving || index === 0}
                      aria-label={`Move ${selected[index]?.title ?? "item"} earlier`}
                      onClick={() => move(index, -1)}
                    >
                      ↑
                    </button>
                    <button
                      disabled={saving || index === value.itemIds.length - 1}
                      aria-label={`Move ${selected[index]?.title ?? "item"} later`}
                      onClick={() => move(index, 1)}
                    >
                      ↓
                    </button>
                    <button
                      disabled={saving}
                      aria-label={`Remove ${selected[index]?.title ?? "unavailable item"}`}
                      onClick={() =>
                        onChange({
                          ...value,
                          itemIds: value.itemIds.filter((x) => x !== id),
                        })
                      }
                    >
                      Remove
                    </button>
                  </>
                )}
              </div>
            ))}
          </div>
          {!readOnly && (
            <label>
              Add a piece
              <select
                value=""
                disabled={saving}
                onChange={(e) => {
                  if (e.target.value)
                    onChange({
                      ...value,
                      itemIds: [...value.itemIds, e.target.value],
                    });
                }}
              >
                <option value="">Choose from your closet</option>
                {items
                  .filter((i) => !value.itemIds.includes(i.id))
                  .map((i) => (
                    <option value={i.id} key={i.id}>
                      {i.title}
                    </option>
                  ))}
              </select>
            </label>
          )}
          {onSave && !readOnly && (
            <button
              className={styles.primary}
              disabled={
                saving ||
                !value.itemIds.length ||
                !value.title.trim() ||
                selected.some((i) => !i)
              }
              onClick={() => void save()}
            >
              {saving ? "Saving…" : "Save look"}
            </button>
          )}
          <p role="status" className={styles.muted}>
            {message}
          </p>
        </div>
      </div>
    </section>
  );
}

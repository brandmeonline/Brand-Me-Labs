"use client";
import { useEffect, useRef, useState } from "react";
import type { ClosetItem } from "../spatial/types";
import { fidelityLabels, groupLabels, statusLabels } from "../spatial/types";
import styles from "../spatial/spatial.module.css";
const rowHeight = 102,
  overscan = 3;
export function VirtualWardrobe({
  items,
  onSelect,
  selectedId,
}: {
  items: ClosetItem[];
  onSelect: (id: string) => void;
  selectedId?: string;
}) {
  const viewport = useRef<HTMLDivElement>(null),
    [scroll, setScroll] = useState(0),
    [focused, setFocused] = useState<string>();
  useEffect(() => {
    if (viewport.current) viewport.current.scrollTop = 0;
    setScroll(0);
  }, [items]);
  const start = Math.max(0, Math.floor(scroll / rowHeight) - overscan),
    end = Math.min(items.length, start + 4 + overscan * 2);
  const visible = items
    .slice(start, end)
    .map((item, i) => ({ item, index: start + i }));
  const focusIndex = items.findIndex((i) => i.id === focused);
  if (focusIndex >= 0 && !visible.some((v) => v.index === focusIndex))
    visible.push({ item: items[focusIndex], index: focusIndex });
  function jump(index: number) {
    const i = Math.max(0, Math.min(items.length - 1, index));
    if (!viewport.current || !items[i]) return;
    viewport.current.scrollTop = i * rowHeight;
    setScroll(i * rowHeight);
    setFocused(items[i].id);
    requestAnimationFrame(() =>
      viewport.current
        ?.querySelector<HTMLButtonElement>(`[data-index="${i}"] button`)
        ?.focus(),
    );
  }
  return (
    <div>
      <p className={styles.count}>
        {items.length} items · Arrow keys, Home and End move through the list.
      </p>
      <div
        className={styles.listViewport}
        ref={viewport}
        role="list"
        aria-label="Wardrobe items"
        tabIndex={0}
        onScroll={(e) => setScroll(e.currentTarget.scrollTop)}
      >
        {!items.length && (
          <p className={styles.notice}>
            No items here yet. Add something or adjust your search.
          </p>
        )}
        <div style={{ height: items.length * rowHeight, position: "relative" }}>
          {visible.map(({ item, index }) => (
            <div
              key={item.id}
              className={styles.itemRow}
              role="listitem"
              aria-setsize={items.length}
              aria-posinset={index + 1}
              style={{ top: index * rowHeight }}
              data-index={index}
            >
              <img
                src={item.posterUrl}
                alt=""
                width="70"
                height="80"
                loading="lazy"
              />
              <div>
                <strong>{item.title}</strong>
                <p className={styles.muted}>
                  {statusLabels[item.status]} ·{" "}
                  {groupLabels[item.placement.semanticGroup]}
                  {item.placement.semanticGroup !== "unplaced"
                    ? `, slot ${item.placement.slotId + 1}`
                    : ""}
                </p>
                <span className={styles.fidelity}>
                  {fidelityLabels[item.fidelity]}
                </span>
              </div>
              <button
                aria-pressed={selectedId === item.id}
                onFocus={() => setFocused(item.id)}
                onClick={() => onSelect(item.id)}
                onKeyDown={(e) => {
                  const moves: { [key: string]: number } = {
                    ArrowDown: index + 1,
                    ArrowUp: index - 1,
                    Home: 0,
                    End: items.length - 1,
                  };
                  if (e.key in moves) {
                    e.preventDefault();
                    jump(moves[e.key]);
                  }
                }}
              >
                Select<span className={styles.srOnly}> {item.title}</span>
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

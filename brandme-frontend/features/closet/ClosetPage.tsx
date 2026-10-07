"use client";
import { useMemo, useState } from "react";
import { useCloset } from "./useCloset";
import { VirtualWardrobe } from "./VirtualWardrobe";
import { eligibleGroups, roomById, rooms } from "../spatial/catalog";
import { RoomViewport } from "../spatial/RoomViewport";
import { useMotionPreference } from "../spatial/useMotionPreference";
import {
  fidelityLabels,
  groupLabels,
  statusLabels,
  type ItemStatus,
  type SemanticGroup,
} from "../spatial/types";
import type { ClosetRepository } from "./repository";
import styles from "../spatial/spatial.module.css";
export default function ClosetPage({
  repository,
  initialItemId,
  settings = false,
}: {
  repository?: ClosetRepository;
  initialItemId?: string;
  settings?: boolean;
}) {
  const { snapshot, error, setError, commit, persistenceLabel, refresh } =
      useCloset(repository),
    [selectedId, setSelectedId] = useState(initialItemId),
    [search, setSearch] = useState(""),
    [status, setStatus] = useState<ItemStatus | "all">("all"),
    [fallback, setFallback] = useState(""),
    [group, setGroup] = useState<SemanticGroup>("rail.left"),
    [slot, setSlot] = useState(0),
    [placing, setPlacing] = useState(false),
    [message, setMessage] = useState(""),
    [busy, setBusy] = useState(false);
  const reducedMotion = useMotionPreference(snapshot?.reducedMotion);
  const filtered = useMemo(
    () =>
      snapshot?.items.filter(
        (i) =>
          (status === "all" || i.status === status) &&
          i.title.toLowerCase().includes(search.toLowerCase()),
      ) ?? [],
    [snapshot?.items, status, search],
  );
  if (!snapshot)
    return (
      <section className={styles.root}>
        <h1>My Closet</h1>
        <p role="status" className={styles.notice}>
          {error || "Opening your wardrobe…"}
        </p>
        {error && <button onClick={() => void refresh()}>Retry</button>}
      </section>
    );
  const room = roomById(snapshot.roomId),
    selected = snapshot.items.find((i) => i.id === selectedId),
    simple = snapshot.simpleView || !!fallback;
  function select(id: string) {
    setSelectedId(id);
    setPlacing(false);
    const item = snapshot!.items.find((i) => i.id === id);
    if (item) {
      setGroup(item.placement.semanticGroup);
      setSlot(item.placement.slotId);
    }
  }
  async function move() {
    if (!selected || busy) return;
    setBusy(true);
    try {
      await commit({
        type: "move",
        itemId: selected.id,
        expectedItemVersion: selected.version,
        group,
        slot,
      });
      setMessage(
        `Moved ${selected.title} to ${groupLabels[group]}${group === "unplaced" ? "" : `, slot ${slot + 1}`}.`,
      );
      setPlacing(false);
    } catch {
    } finally {
      setBusy(false);
    }
  }
  function onKey(event: React.KeyboardEvent) {
    if (!placing) return;
    if (event.key === "Escape") {
      event.preventDefault();
      setPlacing(false);
      setMessage("Placement cancelled. Your saved position is unchanged.");
    }
    if (
      ["ArrowRight", "ArrowDown", "ArrowLeft", "ArrowUp"].includes(event.key)
    ) {
      event.preventDefault();
      const capacity = room.groups.find((g) => g.id === group)?.capacity ?? 1;
      setSlot(
        (n) =>
          (n +
            (["ArrowRight", "ArrowDown"].includes(event.key)
              ? 1
              : capacity - 1)) %
          capacity,
      );
    }
    if (
      event.key === "Enter" &&
      event.target instanceof HTMLButtonElement === false
    ) {
      event.preventDefault();
      void move();
    }
  }
  return (
    <section className={styles.root} aria-label="My Closet">
      <header className={styles.header}>
        <div>
          <p className={styles.eyebrow}>Your wardrobe, your world</p>
          <h1>{settings ? "Make room for you" : room.title}</h1>
          <p className={styles.muted}>
            {persistenceLabel} · Fictional starter pieces
          </p>
        </div>
        <div className={styles.toolbar}>
          <button
            aria-pressed={!simple}
            onClick={() => {
              setFallback("");
              void commit({ type: "preferences", simpleView: false }).catch(
                () => {},
              );
            }}
          >
            3D room
          </button>
          <button
            aria-pressed={simple}
            onClick={() =>
              void commit({ type: "preferences", simpleView: true }).catch(
                () => {},
              )
            }
          >
            Simple View
          </button>
          <a className={`${styles.button} ${styles.primary}`} href="/add">
            ＋ Add item
          </a>
        </div>
      </header>
      <div className={styles.toolbar}>
        <label>
          Room environment
          <select
            value={room.id}
            onChange={(e) =>
              void commit({ type: "theme", roomId: e.target.value })
                .then(() =>
                  setMessage(
                    "Room saved. Items without a matching destination are in your Unplaced tray.",
                  ),
                )
                .catch(() => {})
            }
          >
            {rooms.map((r) => (
              <option key={r.id} value={r.id}>
                {r.title}
              </option>
            ))}
          </select>
        </label>
        <label className={styles.checkbox}>
          <input
            type="checkbox"
            checked={snapshot.reducedMotion}
            onChange={(e) =>
              void commit({
                type: "preferences",
                reducedMotion: e.target.checked,
              }).catch(() => {})
            }
          />
          Reduce motion
        </label>
        <a href="/style">Style my pieces ↗</a>
      </div>
      {settings && (
        <div className={styles.notice}>
          Your environment and layout are private. Room changes keep item
          identities, status, and matching semantic slots. Sharing is available
          through the host’s permission-controlled collection flow.
        </div>
      )}
      {error && (
        <div className={`${styles.notice} ${styles.error}`} role="alert">
          {error}
          <button onClick={() => setError("")}>Dismiss</button>
        </div>
      )}
      {fallback && (
        <p className={styles.notice} role="status">
          {fallback}
        </p>
      )}
      <div className={styles.divider} />
      <div className={styles.workspace}>
        <div>
          {!simple && (
            <RoomViewport
              room={room}
              items={filtered}
              selectedId={selectedId}
              onSelect={select}
              onFallback={setFallback}
              namedView={snapshot.namedView}
              reducedMotion={reducedMotion}
              simpleView={simple}
            />
          )}
          {!simple && (
            <div className={styles.sceneTools} aria-label="Named camera views">
              {room.views.map((view) => (
                <button
                  key={view.id}
                  disabled={reducedMotion && view.id !== "room"}
                  aria-pressed={snapshot.namedView === view.id}
                  onClick={() =>
                    void commit({
                      type: "preferences",
                      namedView: view.id,
                    }).catch(() => {})
                  }
                >
                  {view.name}
                </button>
              ))}
              <span className={styles.muted}>
                Bounded capsule · all items remain below
              </span>
            </div>
          )}
          <div className={styles.filters}>
            <label className={styles.srOnly} htmlFor="wardrobe-search">
              Search your closet
            </label>
            <input
              id="wardrobe-search"
              placeholder="Find a piece…"
              type="search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
            <label>
              <span className={styles.srOnly}>Closet status</span>
              <select
                aria-label="Closet status"
                value={status}
                onChange={(e) =>
                  setStatus(e.target.value as ItemStatus | "all")
                }
              >
                <option value="all">All pieces</option>
                {Object.entries(statusLabels).map(([key, label]) => (
                  <option key={key} value={key}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <VirtualWardrobe
            items={filtered}
            selectedId={selectedId}
            onSelect={select}
          />
        </div>
        <aside className={styles.inspector} aria-label="Selected item">
          {selected ? (
            <>
              <img
                src={selected.posterUrl}
                width="240"
                height="200"
                alt={selected.title}
              />
              <div className={styles.stack}>
                <span className={styles.fidelity}>
                  {fidelityLabels[selected.fidelity]}
                </span>
                <h2>{selected.title}</h2>
                <p className={styles.muted}>
                  {statusLabels[selected.status]} ·{" "}
                  {selected.source === "fictional_catalog"
                    ? "Fictional catalog item"
                    : "Self-declared item"}
                </p>
              </div>
              <p className={styles.muted}>
                {groupLabels[selected.placement.semanticGroup]}
                {selected.placement.semanticGroup === "unplaced"
                  ? ""
                  : ` · Slot ${selected.placement.slotId + 1}`}
              </p>
              <div className={styles.row}>
                <a className={styles.button} href={`/try/${selected.id}`}>
                  Inspect / Try
                </a>
                <a className={styles.button} href="/style">
                  Style this
                </a>
              </div>
              <div className={styles.field} onKeyDown={onKey}>
                {!placing ? (
                  <button
                    onClick={() => {
                      setGroup(selected.placement.semanticGroup);
                      setSlot(selected.placement.slotId);
                      setPlacing(true);
                    }}
                  >
                    Move item
                  </button>
                ) : (
                  <>
                    <label>
                      Destination
                      <select
                        aria-label="Placement destination"
                        value={group}
                        onChange={(e) => {
                          setGroup(e.target.value as SemanticGroup);
                          setSlot(0);
                        }}
                      >
                        {eligibleGroups(selected.category, room).map((g) => (
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
                        aria-label="Placement slot"
                        value={slot}
                        onChange={(e) => setSlot(Number(e.target.value))}
                      >
                        {Array.from(
                          {
                            length:
                              room.groups.find((g) => g.id === group)
                                ?.capacity ?? 1,
                          },
                          (_, i) => (
                            <option key={i} value={i}>
                              {i + 1}
                              {snapshot.items.some(
                                (x) =>
                                  x.id !== selected.id &&
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
                    <p className={styles.muted}>
                      Arrow keys choose a slot. Enter saves. Escape cancels.
                    </p>
                    <button
                      className={styles.primary}
                      disabled={busy}
                      onClick={() => void move()}
                    >
                      Save placement
                    </button>
                    <button disabled={busy} onClick={() => setPlacing(false)}>
                      Cancel
                    </button>
                  </>
                )}
              </div>
              <div className={styles.field}>
                <label>
                  Care and styling notes
                  <textarea
                    key={selected.id + selected.version}
                    defaultValue={selected.notes}
                    maxLength={2000}
                    onBlur={(e) => {
                      if (e.target.value !== selected.notes)
                        void commit({
                          type: "notes",
                          itemId: selected.id,
                          expectedItemVersion: selected.version,
                          notes: e.target.value,
                        })
                          .then(() => setMessage("Notes saved."))
                          .catch(() => {});
                    }}
                  />
                </label>
              </div>
            </>
          ) : (
            <>
              <p className={styles.eyebrow}>A place for every piece</p>
              <h2>Wear what feels like you.</h2>
              <p className={styles.muted}>
                Select a garment in the room or list to inspect, organize, or
                build a look.
              </p>
              <a className={styles.button} href="/add">
                Add something I own
              </a>
            </>
          )}
        </aside>
      </div>
      <p role="status" className={styles.muted}>
        {message}
      </p>
    </section>
  );
}

"use client";
import { useMemo, useRef, useState } from "react";
import { useCloset } from "./useCloset";
import { VirtualWardrobe } from "./VirtualWardrobe";
import { eligibleGroups, roomById, rooms } from "../spatial/catalog";
import { RoomViewport } from "../spatial/RoomViewport";
import { SavedCameraViews } from "../spatial/SavedCameraViews";
import type { CameraPose } from "../spatial/cameraPreferences";
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
    [busy, setBusy] = useState(false),
    [picked, setPicked] = useState<Set<string>>(() => new Set()),
    [capsuleId, setCapsuleId] = useState("all"),
    [capsuleName, setCapsuleName] = useState("");
  const reducedMotion = useMotionPreference(snapshot?.reducedMotion);
  const currentCamera = useRef<
    { roomId: string; pose: CameraPose } | undefined
  >(undefined);
  const [cameraRequest, setCameraRequest] = useState<
    (CameraPose & { revision: number; roomId: string }) | undefined
  >();
  const filtered = useMemo(() => {
    const capsule = snapshot?.capsules?.find((c) => c.id === capsuleId);
    const members = capsule ? new Set(capsule.itemIds) : undefined;
    return (
      snapshot?.items.filter(
        (i) =>
          (!members || members.has(i.id)) &&
          (status === "all" || i.status === status) &&
          i.title.toLowerCase().includes(search.toLowerCase()),
      ) ?? []
    );
  }, [snapshot?.items, snapshot?.capsules, capsuleId, status, search]);
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
  function beginPlacement(id: string) {
    select(id);
    setPlacing(true);
    setMessage(
      "Placement mode. Drop on an empty destination, or choose a slot and save. Escape cancels.",
    );
  }
  async function move(destination = group, targetSlot = slot) {
    if (!selected || busy) return;
    setBusy(true);
    try {
      await commit({
        type: "move",
        itemId: selected.id,
        expectedItemVersion: selected.version,
        group: destination,
        slot: targetSlot,
      });
      setMessage(
        `Moved ${selected.title} to ${groupLabels[destination]}${destination === "unplaced" ? "" : `, slot ${targetSlot + 1}`}.`,
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
    <section
      className={styles.root}
      aria-label="My Closet"
      onKeyDown={(e) => {
        if (!e.defaultPrevented && placing && e.key === "Escape") {
          setPlacing(false);
          setMessage("Placement cancelled. Your saved position is unchanged.");
        }
      }}
    >
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
            + Add item
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
              items={snapshot.items}
              matchingIds={filtered.map((i) => i.id)}
              selectedId={selectedId}
              onSelect={select}
              onFallback={setFallback}
              namedView={snapshot.namedView}
              cameraRequest={
                cameraRequest?.roomId === room.id ? cameraRequest : undefined
              }
              onCameraPose={(pose) => {
                currentCamera.current = { roomId: room.id, pose };
              }}
              reducedMotion={reducedMotion}
              simpleView={simple}
            />
          )}
          {!simple && (
            <div className={styles.sceneTools} aria-label="Named camera views">
              {room.views.map((view) => (
                <button
                  key={view.id}
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
          {!simple && (
            <SavedCameraViews
              roomId={room.id}
              getPose={() =>
                currentCamera.current?.roomId === room.id
                  ? currentCamera.current.pose
                  : undefined
              }
              onChoose={(pose) =>
                setCameraRequest({
                  ...pose,
                  roomId: room.id,
                  revision: Date.now(),
                })
              }
            />
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
          <div className={styles.toolbar}>
            <label>
              Capsule
              <select
                aria-label="Capsule"
                value={capsuleId}
                onChange={(e) => setCapsuleId(e.target.value)}
              >
                <option value="all">All capsules</option>
                {snapshot.capsules?.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.title}
                  </option>
                ))}
              </select>
            </label>
            {capsuleId !== "all" && (
              <button
                disabled={busy}
                onClick={async () => {
                  setBusy(true);
                  try {
                    await commit({ type: "delete_capsule", capsuleId });
                    setCapsuleId("all");
                    setMessage(
                      "Capsule removed. Its items remain in your wardrobe.",
                    );
                  } catch {
                  } finally {
                    setBusy(false);
                  }
                }}
              >
                Remove capsule
              </button>
            )}
          </div>
          {!!picked.size && (
            <div className={styles.notice} aria-label="Selected pieces tray">
              <p>
                {picked.size} selected, including selections outside this
                filter.
              </p>
              <div className={styles.toolbar}>
                <label>
                  Capsule name
                  <input
                    disabled={busy}
                    value={capsuleName}
                    maxLength={80}
                    onChange={(e) => setCapsuleName(e.target.value)}
                  />
                </label>
                <button
                  disabled={busy || !capsuleName.trim()}
                  onClick={async () => {
                    setBusy(true);
                    try {
                      const result = await commit({
                        type: "create_capsule",
                        title: capsuleName,
                        itemIds: [...picked],
                      });
                      setCapsuleId(
                        result.snapshot.capsules?.at(-1)?.id ?? "all",
                      );
                      setPicked(new Set());
                      setCapsuleName("");
                      setMessage(
                        "Capsule saved. Item status and ownership are unchanged.",
                      );
                    } catch {
                    } finally {
                      setBusy(false);
                    }
                  }}
                >
                  Save capsule
                </button>
                <button disabled={busy} onClick={() => setPicked(new Set())}>
                  Clear selection
                </button>
              </div>
            </div>
          )}
          <VirtualWardrobe
            items={filtered}
            selectedId={selectedId}
            onSelect={select}
            onBeginPlacement={beginPlacement}
            pickedIds={picked}
            selectionDisabled={busy}
            onTogglePick={(id) =>
              setPicked((previous) => {
                const next = new Set(previous);
                if (next.has(id)) next.delete(id);
                else next.add(id);
                return next;
              })
            }
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
                    <div
                      className={styles.dropSlots}
                      aria-label="Drop destinations"
                    >
                      {eligibleGroups(selected.category, room).flatMap(
                        (anchor) =>
                          Array.from(
                            { length: anchor.capacity },
                            (_, index) => {
                              const occupied = snapshot.items.some(
                                (i) =>
                                  i.id !== selected.id &&
                                  i.placement.semanticGroup === anchor.id &&
                                  i.placement.slotId === index,
                              );
                              return (
                                <button
                                  key={`${anchor.id}:${index}`}
                                  disabled={busy || occupied}
                                  data-drop-group={anchor.id}
                                  data-drop-slot={index}
                                  onDragOver={(e) => {
                                    if (
                                      e.dataTransfer.types.includes(
                                        "application/x-brandme-wardrobe-item",
                                      )
                                    ) {
                                      e.preventDefault();
                                      e.dataTransfer.dropEffect = "move";
                                    }
                                  }}
                                  onDrop={(e) => {
                                    e.preventDefault();
                                    if (
                                      e.dataTransfer.getData(
                                        "application/x-brandme-wardrobe-item",
                                      ) === selected.id
                                    )
                                      void move(anchor.id, index);
                                  }}
                                  onClick={() => {
                                    setGroup(anchor.id);
                                    setSlot(index);
                                  }}
                                >
                                  {groupLabels[anchor.id]} · {index + 1}
                                  {occupied ? " · occupied" : ""}
                                </button>
                              );
                            },
                          ),
                      )}
                    </div>
                    <p className={styles.muted}>
                      Drag the item image onto an empty destination to save.
                      Clicking a destination selects it for confirmation. Arrow
                      keys choose a slot. Enter saves. Escape cancels.
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

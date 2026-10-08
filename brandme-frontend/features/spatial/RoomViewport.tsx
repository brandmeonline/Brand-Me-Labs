"use client";
import {
  Component,
  lazy,
  Suspense,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import type { SceneCanvasProps } from "./SceneCanvas";
import { projectRoomPoint } from "./cameraPreferences";
import type { Vector3 } from "./types";
import styles from "./spatial.module.css";
const SceneCanvas = lazy(() => import("./SceneCanvas"));
class SceneBoundary extends Component<
  { children: ReactNode; fallback: ReactNode; onFailure: () => void },
  { failed: boolean }
> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  componentDidCatch() {
    this.props.onFailure();
  }
  render() {
    return this.state.failed ? this.props.fallback : this.props.children;
  }
}
export function RoomViewport(
  props: SceneCanvasProps & {
    simpleView: boolean;
    pendingPlacement?: {
      position: Vector3;
      poster: string;
      title: string;
      label: string;
    };
  },
) {
  const [supported, setSupported] = useState(false),
    [checked, setChecked] = useState(false),
    [readyRoom, setReadyRoom] = useState(""),
    [displayRoom, setDisplayRoom] = useState(props.room),
    [phase, setPhase] = useState("steady"),
    [aspect, setAspect] = useState(1.6);
  const host = useRef<HTMLDivElement>(null),
    previousItems = useRef(props.items);
  const sameRoom = displayRoom.id === props.room.id;
  if (sameRoom) previousItems.current = props.items;
  useEffect(() => {
    const observer = new ResizeObserver((entries) => {
      const r = entries[0]?.contentRect;
      if (r?.height) setAspect(r.width / r.height);
    });
    if (host.current) observer.observe(host.current);
    return () => observer.disconnect();
  }, []);
  useEffect(() => {
    if (props.reducedMotion || props.simpleView) {
      setDisplayRoom(props.room);
      setPhase("steady");
      return;
    }
    if (props.room.id === displayRoom.id) {
      setPhase("steady");
      return;
    }
    setPhase("out");
    const swap = setTimeout(() => {
      setDisplayRoom(props.room);
      setPhase("in");
    }, 225);
    const finish = setTimeout(() => setPhase("steady"), 450);
    return () => {
      clearTimeout(swap);
      clearTimeout(finish);
    };
  }, [props.room.id, props.reducedMotion, props.simpleView]);
  useEffect(() => {
    const canvas = document.createElement("canvas");
    const context = canvas.getContext("webgl2");
    setSupported(!!context);
    context?.getExtension("WEBGL_lose_context")?.loseContext();
    setChecked(true);
  }, []);
  const poster = (
    <img
      className={styles.scenePoster}
      src={displayRoom.poster}
      width="1440"
      height="900"
      alt={`${displayRoom.title}. Original room preview; use the list below for your current items.`}
    />
  );
  return (
    <>
      <div
        className={styles.sceneWrap}
        ref={host}
        data-room-ready={readyRoom === props.room.id && sameRoom}
        data-room-phase={phase}
        data-displayed-room={displayRoom.id}
      >
        <div
          className={styles.roomStage}
          style={{
            opacity: phase === "out" ? 0 : 1,
            transition: props.reducedMotion ? "none" : "opacity 225ms ease",
          }}
        >
          {checked && supported && !props.simpleView ? (
            <SceneBoundary
              fallback={poster}
              onFailure={() =>
                props.onFallback(
                  "Graphics are unavailable. Simple View remains fully usable.",
                )
              }
            >
              <Suspense fallback={poster}>
                <SceneCanvas
                  {...props}
                  room={displayRoom}
                  items={sameRoom ? props.items : previousItems.current}
                  onReady={() => setReadyRoom(displayRoom.id)}
                />
              </Suspense>
            </SceneBoundary>
          ) : (
            poster
          )}
          {checked &&
            supported &&
            !props.simpleView &&
            readyRoom !== displayRoom.id && (
              <div
                style={{
                  position: "absolute",
                  inset: 0,
                  pointerEvents: "none",
                }}
              >
                {poster}
              </div>
            )}
        </div>
        {props.pendingPlacement &&
          (() => {
            const pending = props.pendingPlacement;
            const point = projectRoomPoint(
              props.room,
              pending.position,
              aspect,
            );
            return (
              <div
                className={styles.pendingSlot}
                data-testid="pending-placement"
                style={{ left: `${point.x * 100}%`, top: `${point.y * 100}%` }}
              >
                <img src={pending.poster} alt={`Pending ${pending.title}`} />
                <span>Saving · {pending.label}</span>
              </div>
            );
          })()}
        <span className={styles.sceneCaption}>
          {props.simpleView || !supported
            ? "Room reference · current items in list"
            : readyRoom !== props.room.id
              ? "Loading room · original reference"
              : props.items.some((i) => i.fidelity === "P0")
                ? "Approximate 3D + Photo displays · select a piece"
                : "Approximate 3D · select a garment"}{" "}
          · Original demo
        </span>
      </div>
      {checked && !supported && (
        <p className={styles.notice}>
          3D graphics are unavailable on this device. Simple View supports the
          same organization and styling actions.
        </p>
      )}
    </>
  );
}

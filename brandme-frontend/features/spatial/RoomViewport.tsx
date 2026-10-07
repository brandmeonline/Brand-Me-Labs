"use client";
import {
  Component,
  lazy,
  Suspense,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import type { SceneCanvasProps } from "./SceneCanvas";
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
  props: SceneCanvasProps & { simpleView: boolean },
) {
  const [supported, setSupported] = useState(false),
    [checked, setChecked] = useState(false),
    [readyRoom, setReadyRoom] = useState("");
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
      src={props.room.poster}
      width="1440"
      height="900"
      alt={`${props.room.title}. Original room preview; use the list below for your current items.`}
    />
  );
  return (
    <>
      <div
        className={styles.sceneWrap}
        data-room-ready={readyRoom === props.room.id}
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
                onReady={() => setReadyRoom(props.room.id)}
              />
            </Suspense>
          </SceneBoundary>
        ) : (
          poster
        )}
        {checked &&
          supported &&
          !props.simpleView &&
          readyRoom !== props.room.id && (
            <div
              style={{ position: "absolute", inset: 0, pointerEvents: "none" }}
            >
              {poster}
            </div>
          )}
        <span className={styles.sceneCaption}>
          {props.simpleView || !supported
            ? "Room reference · current items in list"
            : readyRoom !== props.room.id
              ? "Loading room · original reference"
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

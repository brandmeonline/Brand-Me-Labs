"use client";
import { useEffect, useRef } from "react";
import { useFrame, useThree } from "@react-three/fiber";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { Vector3 as V3 } from "three";
import {
  persistCamera,
  restoreCamera,
  validCamera,
  type CameraPose,
} from "./cameraPreferences";
import type { Room, Vector3 } from "./types";

export function CameraRig({
  room,
  view,
  active,
  reducedMotion,
  selected,
  interactive = true,
  cameraRequest,
  onCameraPose,
}: {
  room: Room;
  view: string;
  active: boolean;
  reducedMotion: boolean;
  selected?: { id: string; position: Vector3 };
  interactive?: boolean;
  cameraRequest?: CameraPose & { revision: number };
  onCameraPose?: (pose: CameraPose) => void;
}) {
  const { camera, gl, invalidate, setFrameloop } = useThree();
  const controls = useRef<OrbitControls | null>(null),
    timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const latest = useRef({ room, view, onCameraPose });
  latest.current = { room, view, onCameraPose };
  const animation = useRef<
    | { from: V3; targetFrom: V3; to: V3; targetTo: V3; started: number }
    | undefined
  >(undefined);
  const context = useRef("");
  function report() {
    const c = controls.current;
    if (c)
      latest.current.onCameraPose?.({
        position: camera.position.toArray() as Vector3,
        target: c.target.toArray() as Vector3,
      });
  }
  function go(pose: CameraPose, animate: boolean) {
    const c = controls.current;
    if (!c || !validCamera(pose)) return;
    clearTimeout(timer.current);
    const to = new V3(...pose.position),
      targetTo = new V3(...pose.target);
    if (animate) {
      animation.current = {
        from: camera.position.clone(),
        targetFrom: c.target.clone(),
        to,
        targetTo,
        started: performance.now(),
      };
    } else {
      animation.current = undefined;
      camera.position.copy(to);
      c.target.copy(targetTo);
      c.update();
      report();
    }
    invalidate();
  }
  useEffect(() => {
    const c = new OrbitControls(camera, gl.domElement);
    controls.current = c;
    c.enabled = interactive;
    c.enablePan = false;
    c.enableDamping = false;
    c.minDistance = 1.4;
    c.maxDistance = 6;
    c.minAzimuthAngle = (-55 * Math.PI) / 180;
    c.maxAzimuthAngle = (55 * Math.PI) / 180;
    c.minPolarAngle = Math.PI / 2 - (18 * Math.PI) / 180;
    c.maxPolarAngle = Math.PI / 2 + (12 * Math.PI) / 180;
    const change = () => invalidate();
    const start = () => {
      animation.current = undefined;
      clearTimeout(timer.current);
    };
    const end = () => {
      report();
      clearTimeout(timer.current);
      timer.current = setTimeout(() => {
        const { room, view } = latest.current;
        persistCamera(room.id, view, {
          position: camera.position.toArray() as Vector3,
          target: c.target.toArray() as Vector3,
        });
      }, 1000);
    };
    c.addEventListener("change", change);
    c.addEventListener("start", start);
    c.addEventListener("end", end);
    return () => {
      clearTimeout(timer.current);
      animation.current = undefined;
      c.dispose();
      controls.current = null;
      context.current = "";
    };
  }, [camera, gl, invalidate, interactive]);
  useEffect(() => {
    const chosen = room.views.find((v) => v.id === view) ?? room.views[0];
    const next = `${room.id}:${view}`,
      initial = !context.current || !context.current.startsWith(`${room.id}:`);
    context.current = next;
    go(
      (initial && interactive && restoreCamera(room.id, view)) || chosen,
      !initial && !reducedMotion,
    );
  }, [room.id, view, interactive]);
  useEffect(() => {
    if (cameraRequest) go(cameraRequest, !reducedMotion);
  }, [cameraRequest]);
  useEffect(() => {
    if (!selected || reducedMotion || !interactive) return;
    const target: Vector3 = [
      selected.position[0] * 0.7,
      Math.max(0.8, selected.position[1] - 0.25),
      selected.position[2],
    ];
    go({ target, position: [target[0] * 0.6, 1.55, 3.2] }, true);
  }, [selected?.id]);
  useEffect(() => {
    if (reducedMotion && animation.current)
      go(
        {
          position: animation.current.to.toArray() as Vector3,
          target: animation.current.targetTo.toArray() as Vector3,
        },
        false,
      );
  }, [reducedMotion]);
  useEffect(() => {
    setFrameloop(active ? "demand" : "never");
    if (active) invalidate();
    else animation.current = undefined;
  }, [active, setFrameloop, invalidate]);
  useFrame(() => {
    const a = animation.current,
      c = controls.current;
    if (!a || !c) return;
    const t = Math.min(1, (performance.now() - a.started) / 220),
      eased = 1 - (1 - t) ** 3;
    camera.position.lerpVectors(a.from, a.to, eased);
    c.target.lerpVectors(a.targetFrom, a.targetTo, eased);
    c.update();
    if (t < 1) invalidate();
    else {
      animation.current = undefined;
      report();
    }
  });
  return null;
}

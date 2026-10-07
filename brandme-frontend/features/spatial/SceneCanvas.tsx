"use client";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { useEffect, useMemo, useRef, useState } from "react";
import * as T from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { assets } from "./catalog";
import type { ClosetItem, Room } from "./types";

type Tier = "entry" | "standard" | "desktop";
const limits = {
  entry: { items: 12, calls: 100, triangles: 180000, dpr: 1 },
  standard: { items: 24, calls: 150, triangles: 350000, dpr: 1.5 },
  desktop: { items: 48, calls: 250, triangles: 800000, dpr: 2 },
};
const pool = new Map<
  string,
  {
    refs: number;
    promise: Promise<T.Group>;
    group?: T.Group;
    timer?: ReturnType<typeof setTimeout>;
  }
>();
function dispose(group: T.Group) {
  const textures = new Set<T.Texture>(),
    geometries = new Set<T.BufferGeometry>(),
    materials = new Set<T.Material>();
  group.traverse((o) => {
    if (o instanceof T.Mesh) {
      geometries.add(o.geometry);
      for (const m of Array.isArray(o.material) ? o.material : [o.material]) {
        materials.add(m);
        Object.values(m).forEach((value) => {
          if (value instanceof T.Texture) textures.add(value);
        });
      }
    }
  });
  textures.forEach((t) => {
    const img = t.source.data as { close?: () => void };
    img?.close?.();
    t.dispose();
  });
  materials.forEach((m) => m.dispose());
  geometries.forEach((g) => g.dispose());
}
function acquire(url: string) {
  let entry = pool.get(url);
  if (!entry) {
    const promise = new GLTFLoader().loadAsync(url).then((g) => g.scene);
    entry = { refs: 0, promise };
    pool.set(url, entry);
    promise
      .then((group) => {
        entry!.group = group;
      })
      .catch(() => {});
  }
  entry.refs++;
  clearTimeout(entry.timer);
  return {
    promise: entry.promise,
    release: () => {
      entry!.refs--;
      if (entry!.refs === 0)
        entry!.timer = setTimeout(() => {
          pool.delete(url);
          void entry!.promise.then(dispose).catch(() => {});
        }, 1000);
    },
  };
}
function AssetObject({
  url,
  onFailure,
  onClick,
  onRendered,
}: {
  url: string;
  onFailure: () => void;
  onClick?: () => void;
  onRendered?: () => void;
}) {
  const [object, setObject] = useState<T.Group>();
  const invalidate = useThree((s) => s.invalidate);
  const failure = useRef(onFailure);
  failure.current = onFailure;
  const rendered = useRef(onRendered);
  rendered.current = onRendered;
  useEffect(() => {
    let active = true;
    const lease = acquire(url);
    void lease.promise
      .then((group) => {
        if (active) {
          const instance = group.clone(true);
          let announced = false;
          instance.traverse((o) => {
            if (o instanceof T.Mesh) {
              o.castShadow = true;
              o.receiveShadow = true;
              o.onAfterRender = () => {
                if (!announced && active && rendered.current) {
                  announced = true;
                  queueMicrotask(() => active && rendered.current?.());
                }
              };
            }
          });
          setObject(instance);
          invalidate();
        }
      })
      .catch(() => {
        if (active) failure.current();
      });
    return () => {
      active = false;
      lease.release();
    };
  }, [url, invalidate]);
  return object ? (
    <primitive
      object={object}
      dispose={null}
      onClick={
        onClick
          ? (e: { stopPropagation: () => void }) => {
              e.stopPropagation();
              onClick();
            }
          : undefined
      }
    />
  ) : null;
}
function CameraRig({
  room,
  view,
  active,
}: {
  room: Room;
  view: string;
  active: boolean;
}) {
  const { camera, gl, invalidate, setFrameloop } = useThree();
  const controls = useRef<OrbitControls | undefined>(undefined);
  useEffect(() => {
    const c = new OrbitControls(camera, gl.domElement);
    controls.current = c;
    c.enablePan = false;
    c.enableDamping = false;
    c.minDistance = 1.4;
    c.maxDistance = 6;
    c.minAzimuthAngle = (-55 * Math.PI) / 180;
    c.maxAzimuthAngle = (55 * Math.PI) / 180;
    c.minPolarAngle = Math.PI / 2 - (18 * Math.PI) / 180;
    c.maxPolarAngle = Math.PI / 2 + (12 * Math.PI) / 180;
    c.addEventListener("change", () => invalidate());
    return () => {
      c.dispose();
      controls.current = undefined;
    };
  }, [camera, gl, invalidate]);
  useEffect(() => {
    const chosen = room.views.find((v) => v.id === view) ?? room.views[0];
    camera.position.set(...chosen.position);
    controls.current?.target.set(...chosen.target);
    camera.lookAt(...chosen.target);
    controls.current?.update();
    invalidate();
  }, [room, view, camera, invalidate]);
  useEffect(() => {
    setFrameloop(active ? "demand" : "never");
    if (active) invalidate();
  }, [active, setFrameloop, invalidate]);
  return null;
}
function ContextLoss({ onFallback }: { onFallback: (reason: string) => void }) {
  const gl = useThree((s) => s.gl);
  useEffect(() => {
    const lost = (event: Event) => {
      event.preventDefault();
      onFallback(
        "Graphics were interrupted. Simple View keeps every item and action available.",
      );
    };
    gl.domElement.addEventListener("webglcontextlost", lost);
    return () => gl.domElement.removeEventListener("webglcontextlost", lost);
  }, [gl, onFallback]);
  return null;
}
function Monitor({
  tier,
  onDowngrade,
  onStats,
}: {
  tier: Tier;
  onDowngrade: () => void;
  onStats: (n: string) => void;
}) {
  const slow = useRef(0),
    last = useRef(0);
  useFrame(({ gl, clock }, delta) => {
    if (delta > 0.04 && delta < 0.12) slow.current++;
    else if (delta < 0.04) slow.current = Math.max(0, slow.current - 1);
    if (slow.current > 24 && tier !== "entry") {
      slow.current = 0;
      onDowngrade();
    }
    if (clock.elapsedTime - last.current > 1) {
      last.current = clock.elapsedTime;
      onStats(
        `${gl.info.render.calls} draw calls · ${gl.info.render.triangles.toLocaleString()} triangles`,
      );
    }
  });
  return null;
}
export interface SceneCanvasProps {
  room: Room;
  items: ClosetItem[];
  selectedId?: string;
  onSelect: (id: string) => void;
  onFallback: (reason: string) => void;
  namedView: string;
  reducedMotion: boolean;
  onReady?: () => void;
}
export default function SceneCanvas({
  room,
  items,
  selectedId,
  onSelect,
  onFallback,
  namedView,
  reducedMotion,
  onReady,
}: SceneCanvasProps) {
  const [tier, setTier] = useState<Tier>("entry"),
    [active, setActive] = useState(true),
    [stats, setStats] = useState("Loading room");
  const host = useRef<HTMLDivElement>(null);
  useEffect(() => {
    setTier(
      innerWidth >= 1100 ? "desktop" : innerWidth >= 700 ? "standard" : "entry",
    );
    const visibility = () => setActive(!document.hidden);
    document.addEventListener("visibilitychange", visibility);
    const observer = new IntersectionObserver((entries) =>
      setActive(!document.hidden && !!entries[0]?.isIntersecting),
    );
    if (host.current) observer.observe(host.current);
    return () => {
      document.removeEventListener("visibilitychange", visibility);
      observer.disconnect();
    };
  }, []);
  const shown = useMemo(() => {
    let calls = 12,
      triangles = 20000;
    return items
      .filter(
        (i) =>
          i.placement.semanticGroup !== "unplaced" &&
          i.assetSlug &&
          i.status !== "archive",
      )
      .filter((i) => {
        const a = assets.find((a) => a.slug === i.assetSlug);
        if (!a) return false;
        calls += a.drawCalls ?? 5;
        triangles += a.triangleCount ?? 4000;
        return (
          calls <= limits[tier].calls && triangles <= limits[tier].triangles
        );
      })
      .slice(0, limits[tier].items);
  }, [items, tier]);
  return (
    <div
      ref={host}
      data-scene-count={shown.length}
      data-scene-tier={tier}
      data-scene-stats={stats}
      aria-label={`${room.title}, ${shown.length} visible garments. Use the item list to organize everything.`}
    >
      <Canvas
        camera={{ fov: 38, near: 0.05, far: 40, position: [0, 1.55, 4.8] }}
        dpr={[1, limits[tier].dpr]}
        frameloop="demand"
        shadows={tier !== "entry"}
        gl={{ antialias: tier !== "entry", powerPreference: "low-power" }}
        onCreated={({ gl }) => {
          gl.toneMapping = T.ACESFilmicToneMapping;
          gl.toneMappingExposure = 1.2;
        }}
      >
        <color attach="background" args={["#ede6d9"]} />
        <hemisphereLight args={["#fff8e8", "#797567", 2.1]} />
        <directionalLight
          position={[-3, 4, 4]}
          intensity={4}
          color="#fff2db"
          castShadow={tier !== "entry"}
          shadow-mapSize={[1024, 1024]}
          shadow-camera-left={-4}
          shadow-camera-right={4}
          shadow-camera-top={4}
          shadow-camera-bottom={-4}
          shadow-bias={-0.0003}
          shadow-normalBias={0.02}
        />
        <directionalLight
          position={[4, 2, 1]}
          intensity={1.5}
          color="#e8efff"
        />
        <AssetObject
          key={room.id}
          url={room.glb}
          onRendered={onReady}
          onFailure={() =>
            onFallback(
              "This room could not load. Your items are still available in Simple View.",
            )
          }
        />
        {shown.map((item) => {
          const a = assets.find((a) => a.slug === item.assetSlug)!;
          const p = item.placement;
          return (
            <group
              key={item.id}
              position={p.positionMeters}
              quaternion={p.rotationQuaternion}
              scale={p.uniformScale}
            >
              <AssetObject
                url={a.lowGlb!}
                onFailure={() =>
                  onFallback(
                    "A garment model could not load. Its image and controls are available in Simple View.",
                  )
                }
                onClick={() => onSelect(item.id)}
              />
              {item.id === selectedId && (
                <mesh position={[0, 0.13, 0]} rotation={[Math.PI / 2, 0, 0]}>
                  <torusGeometry args={[0.04, 0.006, 6, 32]} />
                  <meshBasicMaterial color="#62527f" />
                </mesh>
              )}
            </group>
          );
        })}
        <ContextLoss onFallback={onFallback} />
        <CameraRig
          room={room}
          view={reducedMotion ? "room" : namedView}
          active={active}
        />
        <Monitor
          tier={tier}
          onDowngrade={() =>
            setTier((t) => (t === "desktop" ? "standard" : "entry"))
          }
          onStats={setStats}
        />
      </Canvas>
    </div>
  );
}

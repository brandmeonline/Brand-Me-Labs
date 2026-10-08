"use client";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { useEffect, useMemo, useRef, useState } from "react";
import * as T from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { CameraRig } from "./CameraRig";
import type { CameraPose } from "./cameraPreferences";
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
  dimmed = false,
}: {
  url: string;
  onFailure: () => void;
  onClick?: () => void;
  onRendered?: () => void;
  dimmed?: boolean;
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
    const ownedMaterials = new Map<T.Material, T.Material>();
    void lease.promise
      .then((group) => {
        if (active) {
          const instance = group.clone(true);
          let announced = false;
          instance.traverse((o) => {
            if (o instanceof T.Mesh) {
              const copy = (material: T.Material) => {
                let cloned = ownedMaterials.get(material);
                if (!cloned) {
                  cloned = material.clone();
                  cloned.userData = {
                    ...cloned.userData,
                    baseOpacity: material.opacity,
                    baseTransparent: material.transparent,
                    baseDepthWrite: material.depthWrite,
                  };
                  ownedMaterials.set(material, cloned);
                }
                return cloned;
              };
              o.material = Array.isArray(o.material)
                ? o.material.map(copy)
                : copy(o.material);
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
      ownedMaterials.forEach((m) => m.dispose());
      lease.release();
    };
  }, [url, invalidate]);
  useEffect(() => {
    object?.traverse((o) => {
      if (o instanceof T.Mesh)
        for (const material of Array.isArray(o.material)
          ? o.material
          : [o.material]) {
          material.opacity = dimmed ? 0.2 : material.userData.baseOpacity;
          material.transparent = dimmed || material.userData.baseTransparent;
          material.depthWrite = !dimmed && material.userData.baseDepthWrite;
          material.needsUpdate = true;
        }
    });
    invalidate();
  }, [object, dimmed, invalidate]);
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
function PhotoObject({
  url,
  onClick,
  onFailure,
  dimmed = false,
}: {
  url: string;
  onClick: () => void;
  onFailure: () => void;
  dimmed?: boolean;
}) {
  const [texture, setTexture] = useState<T.Texture>();
  const invalidate = useThree((s) => s.invalidate),
    failure = useRef(onFailure);
  failure.current = onFailure;
  useEffect(() => {
    let active = true;
    const map = new T.TextureLoader().load(
      url,
      (t) => {
        if (!active) {
          t.dispose();
          return;
        }
        t.colorSpace = T.SRGBColorSpace;
        setTexture(t);
        invalidate();
      },
      undefined,
      () => active && failure.current(),
    );
    return () => {
      active = false;
      map.dispose();
    };
  }, [url, invalidate]);
  return texture ? (
    <mesh
      position={[0, -0.35, 0.02]}
      onClick={(e) => {
        e.stopPropagation();
        onClick();
      }}
    >
      <planeGeometry args={[0.55, 0.7]} />
      <meshBasicMaterial
        map={texture}
        transparent
        opacity={dimmed ? 0.2 : 1}
        side={T.DoubleSide}
      />
    </mesh>
  ) : null;
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
  matchingIds?: readonly string[];
  interactiveCamera?: boolean;
  cameraRequest?: CameraPose & { revision: number };
  onCameraPose?: (pose: CameraPose) => void;
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
  interactiveCamera = true,
  cameraRequest,
  onCameraPose,
  matchingIds,
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
    return [...items]
      .sort((a, b) => Number(b.id === selectedId) - Number(a.id === selectedId))
      .filter(
        (i) =>
          i.placement.semanticGroup !== "unplaced" && i.status !== "archive",
      )
      .filter((i) => {
        const a = assets.find((a) => a.slug === i.assetSlug);
        calls += a?.drawCalls ?? 1;
        triangles += a?.triangleCount ?? 2;
        return (
          calls <= limits[tier].calls && triangles <= limits[tier].triangles
        );
      })
      .slice(0, limits[tier].items);
  }, [items, tier, selectedId]);
  const matches = useMemo(
    () => (matchingIds ? new Set(matchingIds) : undefined),
    [matchingIds],
  );
  return (
    <div
      ref={host}
      data-scene-count={shown.length}
      data-scene-tier={tier}
      data-scene-dimmed={
        matches ? shown.filter((i) => !matches.has(i.id)).length : 0
      }
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
          const a = assets.find((a) => a.slug === item.assetSlug);
          const p = item.placement;
          return (
            <group
              key={item.id}
              position={p.positionMeters}
              quaternion={p.rotationQuaternion}
              scale={p.uniformScale}
            >
              {a?.lowGlb ? (
                <AssetObject
                  url={a.lowGlb}
                  dimmed={!!matches && !matches.has(item.id)}
                  onFailure={() =>
                    onFallback(
                      "A garment model could not load. Its image and controls are available in Simple View.",
                    )
                  }
                  onClick={() => onSelect(item.id)}
                />
              ) : (
                <PhotoObject
                  dimmed={!!matches && !matches.has(item.id)}
                  url={item.posterUrl}
                  onClick={() => onSelect(item.id)}
                  onFailure={() =>
                    onFallback(
                      "This photo could not load. The item is still available in Simple View.",
                    )
                  }
                />
              )}
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
          view={namedView}
          active={active}
          reducedMotion={reducedMotion}
          interactive={interactiveCamera}
          cameraRequest={cameraRequest}
          onCameraPose={(pose) => {
            if (host.current)
              host.current.dataset.cameraPosition = pose.position.join(",");
            onCameraPose?.(pose);
          }}
          selected={
            shown.some((i) => i.id === selectedId)
              ? {
                  id: selectedId!,
                  position: shown.find((i) => i.id === selectedId)!.placement
                    .positionMeters,
                }
              : undefined
          }
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

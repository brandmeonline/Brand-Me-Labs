"use client";
import { motion } from "motion/react";
import { useEffect } from "react";
import styles from "./spatial.module.css";
export interface PlacementFlight {
  itemId: string;
  poster: string;
  source: { x: number; y: number };
  destination: { x: number; y: number };
}
export function SignaturePlacement({
  flight,
  reducedMotion,
  onDone,
}: {
  flight: PlacementFlight;
  reducedMotion: boolean;
  onDone: () => void;
}) {
  useEffect(() => {
    if (reducedMotion) {
      onDone();
      return;
    }
    const end = () => {
      if (document.hidden) onDone();
    };
    document.addEventListener("visibilitychange", end);
    const timer = setTimeout(onDone, 900);
    return () => {
      clearTimeout(timer);
      document.removeEventListener("visibilitychange", end);
    };
  }, [flight, reducedMotion, onDone]);
  if (reducedMotion) return null;
  const { source: a, destination: b } = flight,
    dx = b.x - a.x,
    dy = b.y - a.y;
  const times = [0, 120, 300, 380, 460, 540, 620, 680, 750, 820, 900].map(
    (t) => t / 900,
  );
  const points = times.map((t) => {
    const ms = t * 900;
    if (ms < 300) return { x: 0, y: ms >= 120 ? -4 : 0 };
    const u = Math.min(1, (ms - 300) / 380),
      v = 1 - u;
    return {
      x: 3 * v * v * u * dx * 0.3 + 3 * v * u * u * dx * 0.8 + u * u * u * dx,
      y:
        3 * v * v * u * (dy * 0.2 - 80) +
        3 * v * u * u * (dy * 0.65 - 45) +
        u * u * u * dy,
    };
  });
  return (
    <motion.div
      className={styles.flight}
      style={{ left: a.x - 55, top: a.y - 70 }}
      aria-hidden="true"
      data-testid="placement-flight"
      data-committed-item={flight.itemId}
      initial={{ x: 0, y: 0, opacity: 1 }}
      animate={{
        x: points.map((p) => p.x),
        y: points.map((p) => p.y),
        scale: [1, 1.02, 1, 0.96, 0.92, 0.85, 0.77, 0.72, 0.72, 0.72, 0.72],
        rotate: [0, 0, 0, 0, 0, 0, 0, 3, -1, 0, 0],
        opacity: [1, 1, 0.85, 1, 1, 1, 1, 1, 1, 1, 0],
      }}
      transition={{ duration: 0.9, times, ease: "linear" }}
    >
      <img src={flight.poster} alt="" />
    </motion.div>
  );
}

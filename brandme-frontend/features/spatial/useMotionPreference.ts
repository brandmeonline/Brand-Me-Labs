"use client";
import { useEffect, useState } from "react";
/** Canonical input is the host preference OR the OS setting: user/OS reduction always wins. */
export function useMotionPreference(requested = false) {
  const [system, setSystem] = useState(true);
  useEffect(() => {
    const query = matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setSystem(query.matches);
    update();
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);
  return requested || system;
}

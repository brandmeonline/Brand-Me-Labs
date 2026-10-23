import type { ReactNode } from "react";
import styles from "../spatial/spatial.module.css";
/** Server route guard: the device-only adapter is permitted only as a demo/guest experience.
 * Foundation must replace it with authenticated loaders/repositories for live environments. */
export function SpatialModeGate({
  children,
  mode,
}: {
  children: ReactNode;
  mode: string | undefined;
}) {
  if (mode === "production" || mode === "sandbox")
    return (
      <section className={styles.root}>
        <p className={styles.eyebrow}>My Closet</p>
        <h1>Your wardrobe connection is not ready.</h1>
        <p className={styles.notice}>
          The authenticated wardrobe service must be connected before this
          environment can save or read your items. Your account data has not
          been replaced with demo pieces.
        </p>
      </section>
    );
  return children;
}

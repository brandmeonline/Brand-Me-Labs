// Development verification harness for the real lane components; never a production entrypoint.
import React from "react";
import { createRoot } from "react-dom/client";
import ClosetPage from "../../brandme-frontend/features/closet/ClosetPage";
import { createGuestClosetRepository } from "../../brandme-frontend/features/closet/repository";
import AddItemPage from "../../brandme-frontend/features/closet/AddItemPage";
import StylePage from "../../brandme-frontend/features/closet/StylePage";
import TryPage from "../../brandme-frontend/features/spatial/TryPage";
const path = location.pathname;
const holdSave = new URLSearchParams(location.search).get("save-hold") === "1";
// Only this development harness injects latency, to exercise pending UI against real guest commits.
const delay = Math.min(
  2500,
  Math.max(
    0,
    Number(new URLSearchParams(location.search).get("save-delay")) || 0,
  ),
);
const guest = createGuestClosetRepository();
const delayedGuest = {
  ...guest,
  commit: async (...args: Parameters<typeof guest.commit>) => {
    if (holdSave && (args[0].type === "add" || args[0].type === "move")) {
      await new Promise<void>((resolve) => {
        window.addEventListener("brandme:test-release-save", () => resolve(), { once: true });
      });
    }
    await new Promise((resolve) => setTimeout(resolve, delay));
    return guest.commit(...args);
  },
};
const screen =
  path === "/add" ? (
    <AddItemPage repository={delay || holdSave ? delayedGuest : undefined} />
  ) : path.startsWith("/try/") ? (
    <TryPage itemId={path.split("/")[2]} />
  ) : path.startsWith("/style") ? (
    <StylePage />
  ) : (
    <ClosetPage repository={delay || holdSave ? delayedGuest : undefined} />
  );
createRoot(document.getElementById("root")!).render(
  <React.StrictMode>{screen}</React.StrictMode>,
);

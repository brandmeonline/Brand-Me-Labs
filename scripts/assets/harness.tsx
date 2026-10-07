// Development verification harness for the real lane components; never a production entrypoint.
import React from "react";
import { createRoot } from "react-dom/client";
import ClosetPage from "../../brandme-frontend/features/closet/ClosetPage";
import AddItemPage from "../../brandme-frontend/features/closet/AddItemPage";
import StylePage from "../../brandme-frontend/features/closet/StylePage";
import TryPage from "../../brandme-frontend/features/spatial/TryPage";
const path = location.pathname;
const screen =
  path === "/add" ? (
    <AddItemPage />
  ) : path.startsWith("/try/") ? (
    <TryPage itemId={path.split("/")[2]} />
  ) : path.startsWith("/style") ? (
    <StylePage />
  ) : (
    <ClosetPage />
  );
createRoot(document.getElementById("root")!).render(
  <React.StrictMode>{screen}</React.StrictMode>,
);

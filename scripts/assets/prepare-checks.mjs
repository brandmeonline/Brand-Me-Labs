import { lstat, symlink } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
const toolsDir = path.dirname(fileURLToPath(import.meta.url));
const frontendModules = path.resolve(
  toolsDir,
  "../../brandme-frontend/node_modules",
);
try {
  await lstat(frontendModules);
  console.log("Frontend dependency directory exists; left unchanged.");
} catch (error) {
  if (error.code !== "ENOENT") throw error;
  await lstat(path.join(toolsDir, "node_modules"));
  await symlink("../scripts/assets/node_modules", frontendModules, "dir");
  console.log(
    "Linked the pinned lane tools for local checks. Remove this generated link before a foundation workspace install.",
  );
}

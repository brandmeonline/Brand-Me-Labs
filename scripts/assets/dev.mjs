import { createServer } from "vite";
import path from "node:path";
import { fileURLToPath } from "node:url";
const toolsDir = path.dirname(fileURLToPath(import.meta.url)),
  root = path.resolve(toolsDir, "../..");
export const server = await createServer({
  root,
  publicDir: path.join(root, "brandme-frontend/public"),
  configFile: false,
  esbuild: { jsx: "automatic" },
  resolve: {
    alias: {
      react: path.join(toolsDir, "node_modules/react"),
      "react-dom": path.join(toolsDir, "node_modules/react-dom"),
    },
    dedupe: ["react", "react-dom"],
  },
  server: { host: "127.0.0.1", port: 4178, strictPort: true },
  plugins: [
    {
      name: "spatial-verification-routes",
      configureServer(server) {
        server.middlewares.use((req, res, next) => {
          if (
            /^\/(closet|add|style|try)(\/[^?.]*)?(\?.*)?$/.test(req.url ?? "")
          )
            req.url = "/scripts/assets/harness.html";
          next();
        });
      },
    },
  ],
});
await server.listen();
console.log(
  "Spatial component verification harness: http://127.0.0.1:4178/closet (foundation shell/API are not part of this harness)",
);

import { createServer } from "vite";
import path from "node:path";
import { fileURLToPath } from "node:url";
const toolsDir = path.dirname(fileURLToPath(import.meta.url)),
  root = path.resolve(toolsDir, "../..");
export const server = await createServer({
  root,
  publicDir: path.join(root, "brandme-frontend/public"),
  configFile: false,
  define: {
    "process.env.BRANDME_AR_DEVICE_TEST": JSON.stringify(
      process.env.BRANDME_AR_DEVICE_TEST ?? "0",
    ),
  },
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
        server.middlewares.use(async (req, res, next) => {
          if (req.url?.startsWith("/try/photo/api")) {
            const { createPhotoService, photoConfig } =
              await server.ssrLoadModule(
                "/brandme-frontend/features/spatial/server/photoService.ts",
              );
            server.photoService ??= createPhotoService(
              photoConfig(
                path.join(root, "brandme-frontend/public"),
                path.join(toolsDir, ".photo-dev"),
              ),
            );
            const url = `http://${req.headers.host}${req.url}`;
            const request = new Request(url, {
              method: req.method,
              headers: req.headers,
              ...(["GET", "HEAD"].includes(req.method)
                ? {}
                : { body: req, duplex: "half" }),
            });
            const result = await server.photoService.handle(request);
            res.writeHead(result.status, Object.fromEntries(result.headers));
            res.end(await result.text());
            return;
          }
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

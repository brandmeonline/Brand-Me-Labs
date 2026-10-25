import path from "node:path";
import {
  createPhotoService,
  photoConfig,
} from "../../../../features/spatial/server/photoService";
export const runtime = "nodejs";
export const dynamic = "force-dynamic";
const service = createPhotoService(
  photoConfig(
    path.join(process.cwd(), "public"),
    path.join(process.cwd(), "../scripts/assets/.photo-dev"),
  ),
);
export const GET = (request: Request) => service.handle(request);
export const POST = (request: Request) => service.handle(request);
export const DELETE = (request: Request) => service.handle(request);

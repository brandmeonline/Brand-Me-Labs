/** LOCAL DEVELOPMENT ONLY. Never import into a client bundle. No production or guest-cloud auth. */
import { createHash, randomBytes, randomUUID } from "node:crypto";
import { readFile, writeFile, mkdir, open, unlink } from "node:fs/promises";
import path from "node:path";
type Config = {
  enabled: boolean;
  project: string;
  region: string;
  token: string;
  retention: string;
  publicDir: string;
  stateDir: string;
  limit: number;
};
type Job = {
  id: string;
  owner: string;
  operation: string;
  digest: string;
  state: "running" | "completed" | "failed" | "cancelled" | "unknown";
  expiresAt: number;
  controller: AbortController;
  image?: string;
  message?: string;
};
const sha = (value: string | Buffer) =>
  createHash("sha256").update(value).digest("hex");
const ttl = 86400000;
const cookieName = "brandme_photo_dev";
export function photoConfig(publicDir: string, stateDir: string): Config {
  return {
    enabled:
      process.env.BRANDME_PHOTO_DEV_ENABLED === "1" &&
      process.env.NODE_ENV !== "production" &&
      !["production", "sandbox"].includes(
        process.env.NEXT_PUBLIC_BRANDME_MODE ?? "",
      ),
    project: process.env.BRANDME_PHOTO_DEV_PROJECT ?? "",
    region: process.env.BRANDME_PHOTO_DEV_REGION ?? "us-central1",
    token: process.env.BRANDME_VERTEX_ACCESS_TOKEN ?? "",
    retention: process.env.BRANDME_PHOTO_RETENTION_NOTICE ?? "",
    publicDir,
    stateDir,
    limit: 10,
  };
}
export function createPhotoService(
  config: Config,
  providerFetch: typeof fetch = fetch,
) {
  const jobs = new Map<string, Job>();
  const sessions = new Set<string>();
  const configured = () =>
    config.enabled &&
    /^[a-z][a-z0-9-]{4,60}$/.test(config.project) &&
    /^[a-z]+-[a-z]+[0-9]$/.test(config.region) &&
    !!config.token &&
    !!config.retention;
  const disclosure = () => ({
    enabled: configured(),
    provider: "Google Virtual Try-On",
    model: "virtual-try-on-001",
    region: config.region,
    retention:
      config.retention || "Provider retention terms have not been configured.",
    testOnly: true,
    maxAttempts: config.limit,
    appRetention:
      "App-held outputs expire after 24 hours or on process restart. Saving keeps a copy on this browser until deleted. Cancelling stops local waiting; it does not guarantee provider cancellation or erase provider copies.",
    unavailable:
      "Provider not connected. Configure a dev project, short-lived server access token, region and retention disclosure. Only the supplied synthetic test image is accepted.",
  });
  async function reserve(owner: string, operation: string, digest: string) {
    await mkdir(config.stateDir, { recursive: true, mode: 0o700 });
    const lock = path.join(config.stateDir, "budget.lock");
    let file;
    try {
      file = await open(lock, "wx", 0o600);
    } catch {
      throw Error(
        "Another reservation is pending. Retry with the same operation ID.",
      );
    }
    try {
      const filename = path.join(config.stateDir, "budget.json");
      let ledger: { key: string; digest: string; day: string }[] = [];
      try {
        ledger = JSON.parse(await readFile(filename, "utf8"));
      } catch (e) {
        if ((e as NodeJS.ErrnoException).code !== "ENOENT")
          throw Error(
            "Budget ledger is unavailable; no provider call was made.",
          );
      }
      const key = sha(operation),
        previous = ledger.find((e) => e.key === key);
      if (previous) {
        if (previous.digest !== digest)
          throw Error("Operation ID already used with different inputs.");
        return false;
      }
      const day = new Date().toISOString().slice(0, 10);
      if (ledger.filter((e) => e.day === day).length >= config.limit)
        throw Error("Daily development attempt limit reached.");
      ledger.push({ key, digest, day });
      await writeFile(filename + ".tmp", JSON.stringify(ledger), {
        mode: 0o600,
      });
      // Atomic rename: a failed reservation cannot lead to an unrecorded spend.
      const { rename } = await import("node:fs/promises");
      await rename(filename + ".tmp", filename);
      return true;
    } finally {
      await file.close();
      await unlink(lock);
    }
  }
  function response(body: unknown, status = 200, cookie?: string) {
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      "Cache-Control": "no-store",
      "X-Content-Type-Options": "nosniff",
    };
    if (cookie)
      headers["Set-Cookie"] =
        `${cookieName}=${cookie}; HttpOnly; SameSite=Strict; Path=/try/photo/api; Max-Age=86400`;
    return new Response(JSON.stringify(body), { status, headers });
  }
  const dto = (job: Job) => ({
    id: job.id,
    state: job.state,
    expiresAt: job.expiresAt,
    image: job.image,
    message: job.message,
    fidelity: "Generative visual preview · not a fit estimate",
  });
  function erase(job: Job) {
    job.controller.abort();
    job.image = undefined;
    job.state = "cancelled";
  }
  async function processJob(job: Job, person: string, product: Buffer) {
    const timer = setTimeout(() => job.controller.abort(), 60000);
    timer.unref?.();
    try {
      const endpoint = `https://${config.region}-aiplatform.googleapis.com/v1/projects/${config.project}/locations/${config.region}/publishers/google/models/virtual-try-on-001:predict`;
      const result = await providerFetch(endpoint, {
        method: "POST",
        redirect: "error",
        headers: {
          Authorization: `Bearer ${config.token}`,
          "Content-Type": "application/json",
        },
        signal: job.controller.signal,
        body: JSON.stringify({
          instances: [
            {
              personImage: { image: { bytesBase64Encoded: person } },
              productImages: [
                { image: { bytesBase64Encoded: product.toString("base64") } },
              ],
            },
          ],
          parameters: { sampleCount: 1 },
        }),
      });
      if (!result.ok)
        throw Error(
          "Provider rejected the request. Check dev access/quota; no automatic retry was made.",
        );
      // Bound response bytes before JSON decoding; never log provider messages/images.
      const reader = result.body?.getReader();
      if (!reader) throw Error("Provider returned no image.");
      const chunks: Uint8Array[] = [];
      let size = 0;
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        size += value.length;
        if (size > 12 * 1024 * 1024) {
          await reader.cancel();
          throw Error("Provider output exceeded the limit.");
        }
        chunks.push(value);
      }
      const data = JSON.parse(Buffer.concat(chunks).toString("utf8"));
      const prediction = data.predictions?.[0];
      if (
        prediction?.mimeType !== "image/png" ||
        typeof prediction.bytesBase64Encoded !== "string"
      )
        throw Error("Provider did not return a supported PNG preview.");
      const image = Buffer.from(prediction.bytesBase64Encoded, "base64");
      if (
        image.length < 24 ||
        image.length > 8 * 1024 * 1024 ||
        image.subarray(0, 8).toString("hex") !== "89504e470d0a1a0a" ||
        image.readUInt32BE(16) * image.readUInt32BE(20) > 16000000
      )
        throw Error("Provider returned an invalid or oversized preview.");
      if (job.state !== "running") return;
      job.image = `data:image/png;base64,${image.toString("base64")}`;
      job.state = "completed";
    } catch (e) {
      if (job.state !== "running") return;
      job.state = job.controller.signal.aborted ? "unknown" : "failed";
      job.message =
        job.state === "unknown"
          ? "Provider outcome unknown after timeout. This attempt remains counted; it will not be retried automatically."
          : e instanceof Error && e.message.startsWith("Provider")
            ? e.message
            : "Provider processing failed. No automatic retry was made.";
    } finally {
      clearTimeout(timer);
    }
  }
  return {
    async handle(request: Request): Promise<Response> {
      const url = new URL(request.url);
      // Next may normalize request.url to its internal hostname. Validate the
      // actual HTTP authority before using it for the browser Origin check.
      const authority = request.headers.get("host");
      if (authority) {
        if (!/^(localhost|127\.0\.0\.1|\[::1\])(?::\d{1,5})?$/.test(authority))
          return response({ error: "Local development endpoint only." }, 403);
        url.host = authority;
      }
      // This dev service may not be exposed as an unauthenticated public upload API.
      if (!["localhost", "127.0.0.1", "[::1]"].includes(url.hostname))
        return response({ error: "Local development endpoint only." }, 403);
      if (!["GET", "POST", "DELETE"].includes(request.method))
        return response({ error: "Method not allowed." }, 405);
      if (
        request.method !== "GET" &&
        request.headers.get("origin") !== url.origin
      )
        return response({ error: "Same-origin request required." }, 403);
      for (const [id, job] of jobs)
        if (job.expiresAt <= Date.now()) {
          erase(job);
          jobs.delete(id);
        }
      let owner = request.headers
        .get("cookie")
        ?.split(";")
        .map((v) => v.trim())
        .find((v) => v.startsWith(cookieName + "="))
        ?.slice(cookieName.length + 1);
      if (request.method === "GET" && !url.searchParams.has("id")) {
        if (!configured()) return response(disclosure());
        if (!owner || !sessions.has(owner)) {
          owner = randomBytes(24).toString("hex");
          sessions.add(owner);
          return response(disclosure(), 200, owner);
        }
        return response(disclosure());
      }
      if (!configured())
        return response({ error: disclosure().unavailable }, 503);
      if (!owner || !sessions.has(owner))
        return response(
          { error: "Open the photo preview controls first." },
          401,
        );
      const id = url.searchParams.get("id");
      if (id) {
        const job = jobs.get(id);
        if (!job || job.owner !== owner)
          return response({ error: "Preview not found or expired." }, 404);
        if (request.method === "DELETE") {
          erase(job);
          return response({
            id,
            state: "cancelled",
            deleted: true,
            providerDeletion: false,
          });
        }
        if (request.method !== "GET")
          return response(
            { error: "Use a new operation for a new preview." },
            405,
          );
        return response(dto(job));
      }
      if (request.method !== "POST")
        return response({ error: "Preview ID required." }, 400);
      try {
        const reader = request.body?.getReader();
        if (!reader) return response({ error: "Image required." }, 400);
        const chunks: Uint8Array[] = [];
        let size = 0;
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          size += value.length;
          if (size > 8 * 1024 * 1024) {
            await reader.cancel();
            return response({ error: "Upload exceeds 8 MB." }, 413);
          }
          chunks.push(value);
        }
        const body = JSON.parse(Buffer.concat(chunks).toString("utf8"));
        if (
          body.consent !== true ||
          body.testOnly !== true ||
          typeof body.operationId !== "string" ||
          !/^[-\w]{8,80}$/.test(body.operationId)
        )
          return response(
            {
              error:
                "Explicit test-image processing consent and operation ID are required.",
            },
            400,
          );
        if (
          !["overshirt", "tee", "knit", "jacket"].includes(body.productSlug) ||
          typeof body.personBase64 !== "string"
        )
          return response(
            {
              error:
                "Choose a supported original garment and the synthetic test image.",
            },
            400,
          );
        const person = Buffer.from(body.personBase64, "base64");
        const approved = await readFile(
          path.join(config.publicDir, "demo/test-person/synthetic-adult.png"),
        );
        if (sha(person) !== sha(approved))
          return response(
            {
              error:
                "This development endpoint accepts only the supplied synthetic fixture. Personal photos are disabled.",
            },
            400,
          );
        const digest = sha(sha(person) + ":" + body.productSlug);
        const previous = [...jobs.values()].find(
          (j) => j.owner === owner && j.operation === body.operationId,
        );
        if (previous) {
          if (previous.digest !== digest)
            return response(
              { error: "Operation ID already used with different inputs." },
              409,
            );
          return response(dto(previous));
        }
        const product = await readFile(
          path.join(config.publicDir, `demo/overlays/${body.productSlug}.png`),
        );
        if (!(await reserve(owner, body.operationId, digest)))
          return response(
            {
              error:
                "This operation was already submitted. Outcome is unknown after restart; no retry was sent.",
            },
            409,
          );
        const job: Job = {
          id: randomUUID(),
          owner,
          operation: body.operationId,
          digest,
          state: "running",
          expiresAt: Date.now() + ttl,
          controller: new AbortController(),
        };
        jobs.set(job.id, job);
        const expiration = setTimeout(() => {
          erase(job);
          jobs.delete(job.id);
        }, ttl);
        expiration.unref?.();
        void processJob(job, person.toString("base64"), product);
        return response(dto(job), 202);
      } catch (e) {
        return response(
          {
            error:
              e instanceof Error &&
              /^(Daily|Another|Operation|Budget)/.test(e.message)
                ? e.message
                : "The development request could not be processed. No automatic retry was made.",
          },
          400,
        );
      }
    },
  };
}

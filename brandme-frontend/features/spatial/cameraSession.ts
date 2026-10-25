import { poseAnchor } from "./poseGeometry";
export type CameraState =
  | "not_started"
  | "permission_requested"
  | "calibrating"
  | "tracking"
  | "low_confidence"
  | "lost"
  | "stopped"
  | "unsupported";
export interface OverlayAnchor {
  x: number;
  y: number;
  width: number;
  height: number;
  angle: number;
}
export class CameraSession {
  private stream?: MediaStream;
  private worker?: Worker;
  private timer?: ReturnType<typeof setInterval>;
  private deadline?: ReturnType<typeof setTimeout>;
  private generation = 0;
  private frameDeadline?: ReturnType<typeof setTimeout>;
  private inFlight = false;
  private smooth?: OverlayAnchor;
  private visibility = () => {
    if (document.hidden) this.stop();
  };
  private exit = () => this.stop();
  constructor(
    private video: HTMLVideoElement,
    private state: (s: CameraState, message?: string) => void,
    private pose: (a: OverlayAnchor | null) => void,
  ) {}
  async start(model: { modelUrl: string; wasmRoot: string }) {
    this.stop();
    const generation = ++this.generation;
    if (
      document.hidden ||
      !isSecureContext ||
      !navigator.mediaDevices?.getUserMedia ||
      !globalThis.Worker ||
      !globalThis.createImageBitmap
    ) {
      this.state(
        "unsupported",
        "A secure browser with local camera and worker support is required.",
      );
      return;
    }
    this.state("permission_requested");
    document.addEventListener("visibilitychange", this.visibility);
    window.addEventListener("pagehide", this.exit);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: {
          facingMode: "user",
          width: { ideal: 640 },
          height: { ideal: 480 },
        },
        audio: false,
      });
      if (generation !== this.generation) {
        stream.getTracks().forEach((t) => t.stop());
        return;
      }
      this.stream = stream;
      stream.getVideoTracks().forEach((track) =>
        track.addEventListener(
          "ended",
          () => {
            if (this.stream === stream) this.stop();
          },
          { once: true },
        ),
      );
      this.video.srcObject = stream;
      await this.video.play();
      if (generation !== this.generation) return;
      this.state("calibrating");
      this.deadline = setTimeout(() => {
        this.stop();
        this.state(
          "unsupported",
          "Local tracking took too long to start. Your camera was stopped.",
        );
      }, 15000);
      this.worker = new Worker("/demo/vision/pose-worker.js");
      this.worker.onmessage = (event) => {
        if (generation !== this.generation) return;
        const m = event.data;
        if (m.type === "ready") {
          clearTimeout(this.deadline);
          this.beginFrames(generation);
        }
        if (m.type === "error") {
          this.stop();
          this.state("unsupported", m.message);
        }
        if (m.type === "pose") {
          this.inFlight = false;
          clearTimeout(this.frameDeadline);
          if (m.count > 1) {
            this.smooth = undefined;
            this.pose(null);
            this.state("low_confidence", "Keep just one person in view.");
          } else this.update(m.landmarks);
        }
      };
      this.worker.onerror = () => {
        if (generation !== this.generation) return;
        this.stop();
        this.state(
          "unsupported",
          "Local pose processing is unavailable. Your camera was stopped.",
        );
      };
      this.worker.postMessage({ type: "init", ...model });
    } catch (error) {
      if (generation === this.generation) {
        this.stop();
        this.state(
          "stopped",
          error instanceof DOMException && error.name === "NotAllowedError"
            ? "Camera permission was denied. You can still inspect your item without a camera."
            : "The camera could not start. No frames were uploaded.",
        );
      }
    }
  }
  private beginFrames(generation: number) {
    if (this.timer) clearInterval(this.timer);
    this.timer = setInterval(async () => {
      if (
        generation !== this.generation ||
        this.inFlight ||
        this.video.readyState < 2
      )
        return;
      this.inFlight = true;
      try {
        const bitmap = await createImageBitmap(this.video);
        if (generation !== this.generation || !this.worker) {
          bitmap.close();
          return;
        }
        this.frameDeadline = setTimeout(() => {
          this.stop();
          this.state(
            "unsupported",
            "Tracking stopped responding. Your camera was stopped.",
          );
        }, 5000);
        this.worker.postMessage(
          { type: "frame", bitmap, timestamp: performance.now() },
          [bitmap],
        );
      } catch {
        if (generation === this.generation) this.inFlight = false;
      }
    }, 50);
  }
  private update(points: { x: number; y: number; visibility?: number }[]) {
    if (!points.length) {
      this.smooth = undefined;
      this.pose(null);
      this.state("lost");
      return;
    }
    const next = poseAnchor(
      points,
      this.video.videoWidth || 640,
      this.video.videoHeight || 480,
    );
    if (!next) {
      this.smooth = undefined;
      this.pose(null);
      this.state("low_confidence");
      return;
    }
    if (this.smooth)
      for (const key of ["x", "y", "width", "height", "angle"] as const) {
        const delta = Math.max(
          -0.07,
          Math.min(0.07, next[key] - this.smooth[key]),
        );
        next[key] = this.smooth[key] + delta * 0.35;
      }
    this.smooth = next;
    this.pose(next);
    this.state("tracking");
  }
  stop() {
    this.generation++;
    clearInterval(this.timer);
    clearTimeout(this.deadline);
    clearTimeout(this.frameDeadline);
    this.timer = undefined;
    this.worker?.postMessage({ type: "stop" });
    this.worker?.terminate();
    this.worker = undefined;
    this.stream?.getTracks().forEach((track) => track.stop());
    this.stream = undefined;
    this.video.pause();
    this.video.srcObject = null;
    this.inFlight = false;
    this.smooth = undefined;
    document.removeEventListener("visibilitychange", this.visibility);
    window.removeEventListener("pagehide", this.exit);
    this.pose(null);
    this.state("stopped");
  }
}

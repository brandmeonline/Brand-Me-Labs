import { FilesetResolver, PoseLandmarker } from "@mediapipe/tasks-vision";
let landmarker: PoseLandmarker | undefined,
  closed = false;
// Only local versioned model/WASM paths are allowed. Frames enter through transferable bitmaps.
self.onmessage = async (event: MessageEvent) => {
  const msg = event.data;
  try {
    if (msg.type === "init") {
      if (
        !/^\/demo\/vision\/[^.][\w/.-]+$/.test(msg.modelUrl) ||
        msg.modelUrl.includes("..") ||
        !msg.wasmRoot.startsWith("/demo/vision/") ||
        msg.wasmRoot.includes("..")
      )
        throw new Error("A local approved model is required.");
      const fileset = await FilesetResolver.forVisionTasks(msg.wasmRoot);
      const detector = await PoseLandmarker.createFromOptions(fileset, {
        baseOptions: { modelAssetPath: msg.modelUrl, delegate: "CPU" },
        runningMode: "VIDEO",
        numPoses: 1,
        minPoseDetectionConfidence: 0.6,
        minTrackingConfidence: 0.65,
        outputSegmentationMasks: false,
      });
      if (closed) {
        detector.close();
        return;
      }
      landmarker = detector;
      self.postMessage({ type: "ready" });
    } else if (msg.type === "frame") {
      const bitmap = msg.bitmap as ImageBitmap;
      try {
        if (!landmarker || closed) return;
        const result = landmarker.detectForVideo(bitmap, msg.timestamp);
        self.postMessage({
          type: "pose",
          landmarks: result.landmarks[0] ?? [],
        });
      } finally {
        bitmap.close();
      }
    } else if (msg.type === "stop") {
      closed = true;
      landmarker?.close();
      landmarker = undefined;
      self.close();
    }
  } catch (error) {
    self.postMessage({
      type: "error",
      message:
        error instanceof Error ? error.message : "Pose processing failed.",
    });
  }
};

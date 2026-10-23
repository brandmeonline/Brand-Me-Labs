/* Classic worker: MediaPipe's WASM loader requires importScripts. All assets are same-origin.
 * Runtime/model pins and integrity: scripts/assets/prepare-vision.py. No frame/network uploads. */
self.exports = {};
let detector, closed = false;
self.onmessage = async ({data: msg}) => {
  try {
    if (msg.type === 'init') {
      if (detector || msg.modelUrl !== '/demo/vision/pose-lite-v1.task' || msg.wasmRoot !== '/demo/vision/0.10.35/wasm') throw Error('Unapproved local model.');
      importScripts('/demo/vision/0.10.35/vision_bundle.js');
      const files = await self.exports.FilesetResolver.forVisionTasks(msg.wasmRoot);
      const model = await self.exports.PoseLandmarker.createFromOptions(files, {
        baseOptions: {modelAssetPath: msg.modelUrl, delegate: 'CPU'}, runningMode: 'VIDEO', numPoses: 2,
        minPoseDetectionConfidence: .6, minPosePresenceConfidence: .65, minTrackingConfidence: .65,
        outputSegmentationMasks: false
      });
      if (closed) { model.close(); return; }
      detector = model; self.postMessage({type: 'ready'});
    } else if (msg.type === 'frame') {
      try {
        if (!detector || closed) return;
        const start = performance.now();
        const result = detector.detectForVideo(msg.bitmap, msg.timestamp);
        self.postMessage({type: 'pose', landmarks: result.landmarks.length === 1 ? result.landmarks[0] : [],
          count: result.landmarks.length, latencyMs: performance.now() - start});
      } finally { msg.bitmap.close(); }
    } else if (msg.type === 'stop') {
      closed = true; detector?.close(); self.close();
    }
  } catch { self.postMessage({type:'error',message:'Local pose processing failed. Camera will stop; use the item image.'}); }
};

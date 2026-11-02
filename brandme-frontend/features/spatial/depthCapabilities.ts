/** Permission-free feature probe. AR support cannot establish depth, IR or body-scan quality.
 * https://www.w3.org/TR/2026/WD-webxr-depth-sensing-1-20260825/#initialization
 * Depth requires an enabled session feature and usable frame data; neither is requested here.
 */
export type DepthProbeEnvironment = {
  secureContext: boolean;
  xr?: { isSessionSupported: (mode: "immersive-ar") => Promise<boolean> };
  depthApiExposed: boolean;
};
export type DepthCapability = {
  state: "insecure" | "no-webxr" | "ar-unavailable" | "ar-available" | "unknown";
  depthApiExposed: boolean;
  depth: "unverified";
  infrared: "unverified";
  captureEnabled: false;
  message: string;
};
export function browserDepthEnvironment(): DepthProbeEnvironment {
  const nav = navigator as Navigator & { xr?: DepthProbeEnvironment["xr"] };
  return { secureContext: window.isSecureContext, xr: nav.xr,
    depthApiExposed: "XRDepthInformation" in window };
}
export async function probeDepthCapability(environment: DepthProbeEnvironment, timeoutMs = 3000): Promise<DepthCapability> {
  const base = { depthApiExposed: environment.depthApiExposed === true, depth: "unverified" as const,
    infrared: "unverified" as const, captureEnabled: false as const };
  if (!environment.secureContext) return { ...base, state: "insecure", message: "A secure connection is required for a browser capability check. Depth and infrared capture remain unavailable." };
  if (!environment.xr || typeof environment.xr.isSessionSupported !== "function")
    return { ...base, state: "no-webxr", message: "This browser does not expose WebXR. Phone hardware, depth and infrared support remain unverified." };
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    const supported = await Promise.race([
      environment.xr.isSessionSupported("immersive-ar"),
      new Promise<never>((_, reject) => { timer = setTimeout(() => reject(Error("timeout")), timeoutMs); }),
    ]);
    if (supported === true) return { ...base, state: "ar-available", message: "This browser reports immersive AR support. Depth and infrared access remain unverified; this does not establish a body scan capability." };
    if (supported === false) return { ...base, state: "ar-unavailable", message: "Immersive AR is unavailable in this browser session. This does not determine the phone's depth or infrared hardware." };
    throw Error("Unrecognized capability response");
  } catch {
    return { ...base, state: "unknown", message: "The browser capability check could not complete. Depth and infrared support remain unknown; you can retry." };
  } finally { if (timer !== undefined) clearTimeout(timer); }
}

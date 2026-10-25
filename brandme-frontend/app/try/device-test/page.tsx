import { NativeDeviceSession } from "../../../features/spatial/NativeDeviceSession";
export default function Page() {
  return (
    <NativeDeviceSession
      enabled={
        process.env.NODE_ENV !== "production" &&
        process.env.NEXT_PUBLIC_BRANDME_MODE === "development" &&
        process.env.BRANDME_AR_DEVICE_TEST === "1"
      }
    />
  );
}

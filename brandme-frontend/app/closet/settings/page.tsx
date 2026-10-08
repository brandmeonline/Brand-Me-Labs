import { SpatialModeGate } from "../../../features/closet/SpatialModeGate";
import ClosetPage from "../../../features/closet/ClosetPage";
export default function Page() {
  return (
    <SpatialModeGate mode={process.env.NEXT_PUBLIC_BRANDME_MODE}>
      <ClosetPage settings />
    </SpatialModeGate>
  );
}

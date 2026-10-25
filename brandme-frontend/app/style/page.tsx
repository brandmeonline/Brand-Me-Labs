import { SpatialModeGate } from "../../features/closet/SpatialModeGate";
import StylePage from "../../features/closet/StylePage";
export default function Page() {
  return (
    <SpatialModeGate mode={process.env.NEXT_PUBLIC_BRANDME_MODE}>
      <StylePage />
    </SpatialModeGate>
  );
}

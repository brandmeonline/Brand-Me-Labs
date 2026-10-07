import { SpatialModeGate } from "../../features/closet/SpatialModeGate";
import AddItemPage from "../../features/closet/AddItemPage";
export default function Page() {
  return (
    <SpatialModeGate mode={process.env.NEXT_PUBLIC_BRANDME_MODE}>
      <AddItemPage />
    </SpatialModeGate>
  );
}

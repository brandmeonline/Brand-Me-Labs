import ScanExperience from "../../../features/spatial/ScanExperience";
import { SpatialModeGate } from "../../../features/closet/SpatialModeGate";

// The anchor/disclosure connector must come from the authenticated host. Until
// that integration exists, expose the honest unavailable state without fixtures.
export default function ScanPage() {
  return (
    <SpatialModeGate mode={process.env.NEXT_PUBLIC_BRANDME_MODE}>
      <ScanExperience />
    </SpatialModeGate>
  );
}

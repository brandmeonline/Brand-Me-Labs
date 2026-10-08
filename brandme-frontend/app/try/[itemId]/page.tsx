import { SpatialModeGate } from "../../../features/closet/SpatialModeGate";
import TryPage from "../../../features/spatial/TryPage";
export default async function Page({
  params,
}: {
  params: Promise<{ itemId: string }> | { itemId: string };
}) {
  const { itemId } = await params;
  return (
    <SpatialModeGate mode={process.env.NEXT_PUBLIC_BRANDME_MODE}>
      <TryPage itemId={itemId} />
    </SpatialModeGate>
  );
}

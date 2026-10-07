import { SpatialModeGate } from "../../../../features/closet/SpatialModeGate";
import ClosetPage from "../../../../features/closet/ClosetPage";
export default async function Page({
  params,
}: {
  params: Promise<{ itemId: string }> | { itemId: string };
}) {
  const { itemId } = await params;
  return (
    <SpatialModeGate mode={process.env.NEXT_PUBLIC_BRANDME_MODE}>
      <ClosetPage initialItemId={itemId} />
    </SpatialModeGate>
  );
}

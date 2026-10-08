import { SpatialModeGate } from "../../../../features/closet/SpatialModeGate";
import StylePage from "../../../../features/closet/StylePage";
export default async function Page({
  params,
}: {
  params: Promise<{ outfitId: string }> | { outfitId: string };
}) {
  const { outfitId } = await params;
  return (
    <SpatialModeGate mode={process.env.NEXT_PUBLIC_BRANDME_MODE}>
      <StylePage outfitId={outfitId} />
    </SpatialModeGate>
  );
}

import { PageHeading } from "@/components/shell/page-heading";
import { ProductDetail } from "@/features/commerce/catalog";
export default async function Page({
  params,
}: {
  params: Promise<{ productId: string }>;
}) {
  const { productId } = await params;
  return (
    <>
      <PageHeading
        eyebrow="Discover / Product"
        title="The details matter."
        description="Exact variants and provider observations, with their limits in view."
      />
      <ProductDetail id={productId} />
    </>
  );
}

import { PageHeading } from '@/components/shell/page-heading'
import { ProductDetail } from '@/features/commerce/catalog'
import { notFound } from 'next/navigation'
export default async function Page({
  params,
}: {
  params: Promise<{ productId: string }>
}) {
  const { productId } = await params
  let id: string
  try {
    id = decodeURIComponent(productId)
  } catch {
    notFound()
  }
  return (
    <>
      <PageHeading
        eyebrow="Discover / Product"
        title="The details matter."
        description="Exact variants and provider observations, with their limits in view."
      />
      <ProductDetail id={id} />
    </>
  )
}

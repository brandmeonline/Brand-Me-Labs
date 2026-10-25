import type { Metadata } from 'next'
import { notFound } from 'next/navigation'
import { PageHeading } from '@/components/shell/page-heading'
import { ComponentGallery } from '@/components/ui/component-gallery'

export const metadata: Metadata = {
  title: 'Component gallery',
  robots: { index: false, follow: false },
}
// No production paths are generated; reject them before a parent loading boundary can stream a 200.
export const dynamic = 'force-static'
export const dynamicParams = false

export function generateStaticParams() {
  return process.env.NODE_ENV === 'development'
    ? [{ example: 'components' }]
    : []
}

export default async function ComponentsPage({
  params,
}: {
  params: Promise<{ example: string }>
}) {
  const { example } = await params
  if (process.env.NODE_ENV !== 'development' || example !== 'components')
    notFound()
  return (
    <>
      <PageHeading
        eyebrow="Brand.Me / Development only"
        title="The small details."
        description="Accessible controls for a wardrobe that feels like you. These are local demonstrations, not connected product journeys."
      />
      <ComponentGallery />
    </>
  )
}

import Link from 'next/link'
import { ArrowLeft, Leaf } from 'lucide-react'
import { PageHeading } from './page-heading'
export function AvailabilityState({
  title,
  description,
}: {
  title: string
  description: string
}) {
  return (
    <>
      <PageHeading eyebrow="Your world, taking shape" title={title} />
      <section className="bm-empty-state">
        <Leaf aria-hidden="true" size={32} strokeWidth={1.3} />
        <h2 className="bm-section-title">This space isn’t available yet.</h2>
        <p>{description}</p>
        <Link className="bm-button bm-button-outline" href="/today">
          <ArrowLeft size={18} aria-hidden="true" /> Back to Today
        </Link>
      </section>
    </>
  )
}

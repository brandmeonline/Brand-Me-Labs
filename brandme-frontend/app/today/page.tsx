import type { Metadata } from 'next'
import Link from 'next/link'
import {
  ArrowUpRight,
  ArrowRight,
  Heart,
  SlidersHorizontal,
} from 'lucide-react'
import { LookIllustration } from '@/components/editorial/look-illustration'
import { PageHeading } from '@/components/shell/page-heading'
export const metadata: Metadata = { title: 'Today' }
export default function TodayPage() {
  return (
    <>
      <PageHeading
        eyebrow="A little inspiration for your day"
        title="Make room for you."
        description="A considered look. A fresh perspective. A place to begin."
      />
      <section className="bm-look-feature" aria-labelledby="look-title">
        <figure className="bm-look-stage">
          <div className="bm-stage-top">
            <span className="bm-eyebrow">The everyday edit</span>
            <span className="bm-status-chip">Illustrated example</span>
          </div>
          <LookIllustration />
          <figcaption>
            Original 2D illustration · fictional garments · not a fit preview
          </figcaption>
        </figure>
        <div className="bm-look-caption">
          <div>
            <p className="bm-eyebrow">Soft tailoring / quiet texture</p>
            <h2 id="look-title" className="bm-editorial-title">
              A quieter kind
              <br />
              of statement.
            </h2>
            <p>
              Soft structure, grounded colors, a little room to move. An example
              to explore before you set your direction.
            </p>
          </div>
          <div className="bm-look-notes">
            <span className="bm-small-heading">The idea behind the look</span>
            <ul>
              <li>A relaxed layer over a simple knit</li>
              <li>Earth tones with a darker foundation</li>
              <li>Everyday pieces with a tailored finish</li>
            </ul>
            <span className="bm-support">
              Editorial inspiration, not a personalized recommendation.
            </span>
          </div>
        </div>
        <div className="bm-action-row">
          <Link className="bm-button" href="/me">
            Find my direction <ArrowUpRight size={18} aria-hidden="true" />
          </Link>
          <Link className="bm-button bm-button-outline" href="/discover">
            Explore Discover <ArrowRight size={17} aria-hidden="true" />
          </Link>
        </div>
      </section>
      <section
        className="bm-secondary-stories"
        aria-label="A space for every part of you"
      >
        <Link href="/circle" className="bm-story-link">
          <Heart size={24} strokeWidth={1.4} aria-hidden="true" />
          <div>
            <h2>Your people. Your perspective.</h2>
            <p>Make space for your circle.</p>
          </div>
          <ArrowUpRight size={20} aria-hidden="true" />
        </Link>
        <Link href="/settings" className="bm-story-link">
          <SlidersHorizontal size={24} strokeWidth={1.4} aria-hidden="true" />
          <div>
            <h2>Comfort looks good on you.</h2>
            <p>Adjust appearance and motion.</p>
          </div>
          <ArrowUpRight size={20} aria-hidden="true" />
        </Link>
      </section>
    </>
  )
}

import Link from 'next/link'
import { ArrowUpRight, ArrowRight } from 'lucide-react'
import { LookIllustration } from '@/components/editorial/look-illustration'
export default function HomePage() {
  return (
    <div className="bm-landing">
      <section className="bm-landing-hero">
        <div className="bm-landing-copy">
          <p className="bm-eyebrow">Be More U.</p>
          <h1>
            A wardrobe
            <br />
            that feels
            <br />
            <em>like you.</em>
          </h1>
          <p>
            Not a new you. More of you.
            <br />A place for your style, your favorite pieces, and the people
            whose taste you trust.
          </p>
          <Link className="bm-button" href="/today">
            Explore my style <ArrowUpRight size={18} aria-hidden="true" />
          </Link>
          <span className="bm-support">
            Take a look around. No account needed.
          </span>
        </div>
        <figure className="bm-landing-art">
          <span className="bm-art-caption">THE EVERYDAY EDIT / 01</span>
          <LookIllustration />
          <figcaption>
            Original style illustration · fictional garments
          </figcaption>
        </figure>
      </section>
      <section className="bm-landing-principles" aria-label="What matters here">
        <div>
          <span>01 / REFLECT</span>
          <h2>Your taste. Your say.</h2>
          <p>A style profile you can understand and shape.</p>
        </div>
        <div>
          <span>02 / REDISCOVER</span>
          <h2>Start with what you love.</h2>
          <p>A fresh perspective on what is already yours.</p>
        </div>
        <div>
          <span>03 / CONNECT</span>
          <h2>Good taste is personal.</h2>
          <p>Make room for the people who know you.</p>
        </div>
      </section>
      <Link className="bm-text-link" href="/settings">
        Make the experience comfortable for you{' '}
        <ArrowRight size={17} aria-hidden="true" />
      </Link>
    </div>
  )
}

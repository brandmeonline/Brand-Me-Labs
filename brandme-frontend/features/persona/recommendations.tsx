import Link from 'next/link'
import type { Recommendations } from './types'
export function RecommendationList({ data }: { data: Recommendations }) {
  const basis: Record<string, string> = {
    neutral_start: 'A neutral starting point. Adjust your style to make it more personal.',
    declared_choices: 'Based on the choices you shared.',
    learned_and_declared: 'Based on your shared choices and the learning you allowed.',
  }
  return <section aria-label="Recommendations" className="bm-flow-stack">
    <p className="bm-support">{Object.hasOwn(basis, data.basis) ? basis[data.basis] : 'Review the reasons shown with each suggestion.'}</p>
    {!data.items?.length && <p>No matching products are available with these preferences. Your saved choices remain in control.</p>}
    {data.items?.map(item => <article className="bm-flow-card" key={item.product_id}>
      <h3><Link href={`/products/${encodeURIComponent(item.product_id)}`}>{item.title}</Link></h3>
      {item.sponsored && <p>Sponsored placement</p>}
      {item.labels.map(label => <p className="bm-support" key={label}>{label}</p>)}
      <ul>{item.reasons.map((reason, i) => <li key={i}>{reason.text ?? reason.explanation ?? 'An explanation is not available for this suggestion.'}</li>)}</ul>
    </article>)}
  </section>
}

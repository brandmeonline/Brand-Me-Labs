import Link from 'next/link'
import type { Recommendations } from './types'
export function RecommendationList({ data }: { data: Recommendations }) {
  return <section aria-label="Recommendations" className="bm-flow-stack">
    <p className="bm-support">{data.basis}</p>
    {!data.items?.length && <p>No matching products are available with these preferences. Your saved choices remain in control.</p>}
    {data.items?.map(item => <article className="bm-flow-card" key={item.product_id}>
      <h3><Link href={`/products/${encodeURIComponent(item.product_id)}`}>{item.title}</Link></h3>
      {item.sponsored && <p>Sponsored placement</p>}
      {item.labels.map(label => <p className="bm-support" key={label}>{label}</p>)}
      <ul>{item.reasons.map((reason, i) => <li key={i}>{reason.text ?? reason.explanation ?? reason.code ?? 'View recommendation evidence'}</li>)}</ul>
    </article>)}
  </section>
}

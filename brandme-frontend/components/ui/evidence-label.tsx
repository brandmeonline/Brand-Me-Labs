type PreviewEvidence =
  | {
      kind:
        | 'photo_display'
        | 'approximate_3d'
        | 'product_3d'
        | 'live_overlay'
        | 'generative_preview'
    }
  | { kind: 'calibrated_fit'; method: string; limits: string }

const labels = {
  photo_display: [
    'Photo display',
    'A product photograph displayed in a scene; not a fit estimate.',
  ],
  approximate_3d: [
    'Approximate 3D',
    'A category representation; product details and fit may differ.',
  ],
  product_3d: [
    'Product 3D model',
    'A product-specific model; it does not by itself establish fit.',
  ],
  live_overlay: [
    'Live visual preview',
    'A body-following overlay; not a sizing or fit assessment.',
  ],
  generative_preview: [
    'Generative preview',
    'An AI-generated illustration; not a sizing or fit assessment.',
  ],
} as const

/** No generic "verified" badge. A fit-estimate label requires the caller's actual method AND limitations. */
export function EvidenceLabel(props: PreviewEvidence) {
  if (props.kind === 'calibrated_fit') {
    if (!props.method?.trim() || !props.limits?.trim())
      return (
        <p className="bm-evidence-label">
          Fit estimate unavailable — method and limits are required.
        </p>
      )
    return (
      <div className="bm-evidence-label">
        <strong>Fit estimate</strong>
        <p>Method: {props.method}</p>
        <p>Limits: {props.limits}</p>
      </div>
    )
  }
  const label = labels[props.kind]
  if (!label)
    return <p className="bm-evidence-label">Preview information unavailable.</p>
  return (
    <div className="bm-evidence-label">
      <strong>{label[0]}</strong>
      <p>{label[1]}</p>
    </div>
  )
}

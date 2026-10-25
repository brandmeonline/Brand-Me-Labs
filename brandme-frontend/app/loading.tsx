export default function Loading() {
  return (
    <div className="bm-loading" role="status" aria-live="polite">
      <span className="bm-eyebrow">One moment</span>
      <p>Opening your space…</p>
      <div className="bm-loading-line" />
      <div className="bm-loading-panel" />
    </div>
  )
}

interface Facet {
  facet_type: string
  facet_payload_preview: Record<string, any>
}

interface FacetListProps {
  facets: Facet[]
}

export default function FacetList({ facets }: FacetListProps) {
  const renderFacetPreview = (facet: Facet) => {
    const preview = facet.facet_payload_preview

    switch (facet.facet_type) {
      case 'ESG':
        return (
          <div className="space-y-1">
            {preview.summary && <p className="text-gray-300">{preview.summary}</p>}
            {preview.rating && (
              <div className="inline-block px-2 py-0.5 bg-green-900/30 border border-green-800 rounded text-xs font-semibold text-green-300">
                Rating: {preview.rating}
              </div>
            )}
          </div>
        )

      case 'ORIGIN':
        return (
          <div className="space-y-1">
            {preview.designer && (
              <p className="text-gray-300">
                <span className="text-gray-500">Designer:</span> {preview.designer}
              </p>
            )}
            {preview.cut_and_sewn && (
              <p className="text-gray-300">
                <span className="text-gray-500">Made in:</span> {preview.cut_and_sewn}
              </p>
            )}
          </div>
        )

      case 'MATERIALS':
        return (
          <div className="space-y-1">
            {preview.composition && (
              <p className="text-gray-300">{preview.composition}</p>
            )}
            {preview.sourcing && (
              <p className="text-sm text-gray-400">{preview.sourcing}</p>
            )}
          </div>
        )

      default:
        return (
          <div className="text-gray-400 text-sm">
            {JSON.stringify(preview, null, 2)}
          </div>
        )
    }
  }

  return (
    <div className="space-y-6">
      {facets.map((facet, index) => (
        <div key={index} className="border-l-2 border-gray-800 pl-4 space-y-2">
          <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wide">
            {facet.facet_type}
          </h3>
          {renderFacetPreview(facet)}
        </div>
      ))}
    </div>
  )
}

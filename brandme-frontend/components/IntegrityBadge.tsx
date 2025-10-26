import { Shield, Lock, CheckCircle } from 'lucide-react'

interface IntegrityBadgeProps {
  status: 'verified' | 'pending' | 'denied'
  cardanoHash?: string
  midnightHash?: string
  escalated?: boolean
}

export default function IntegrityBadge({
  status,
  cardanoHash,
  midnightHash,
  escalated,
}: IntegrityBadgeProps) {
  const truncateHash = (hash: string) => {
    if (!hash || hash.length < 16) return hash
    return `${hash.substring(0, 8)}…${hash.substring(hash.length - 8)}`
  }

  if (escalated || status === 'pending') {
    return (
      <div className="bg-yellow-900/20 border border-yellow-800 rounded-lg p-4">
        <div className="flex items-start gap-3">
          <Lock className="w-5 h-5 text-yellow-400 mt-0.5" />
          <div className="flex-1">
            <h3 className="font-semibold text-yellow-200 mb-1">Visibility Under Review</h3>
            <p className="text-sm text-yellow-300/80">
              This item is pending human governance review. Full passport will be available once approved.
            </p>
          </div>
        </div>
      </div>
    )
  }

  if (status === 'verified') {
    return (
      <div className="bg-green-900/20 border border-green-800 rounded-lg p-4">
        <div className="flex items-start gap-3">
          <Shield className="w-5 h-5 text-green-400 mt-0.5" />
          <div className="flex-1 space-y-2">
            <div className="flex items-center gap-2">
              <CheckCircle className="w-4 h-4 text-green-400" />
              <h3 className="font-semibold text-green-200">Verified On-Chain</h3>
            </div>
            <div className="space-y-1 text-xs text-green-300/80">
              {cardanoHash && (
                <div className="flex gap-2">
                  <span className="text-green-400 font-mono">Cardano:</span>
                  <span className="font-mono">{truncateHash(cardanoHash)}</span>
                </div>
              )}
              {midnightHash && (
                <div className="flex gap-2">
                  <span className="text-green-400 font-mono">Midnight:</span>
                  <span className="font-mono">{truncateHash(midnightHash)}</span>
                </div>
              )}
            </div>
            <p className="text-xs text-green-300/70 pt-1">
              Provenance and sustainability claims logged to immutable audit trail
            </p>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="bg-red-900/20 border border-red-800 rounded-lg p-4">
      <div className="flex items-start gap-3">
        <Shield className="w-5 h-5 text-red-400 mt-0.5" />
        <div className="flex-1">
          <h3 className="font-semibold text-red-200 mb-1">Verification Failed</h3>
          <p className="text-sm text-red-300/80">
            This item could not be verified. Provenance unknown.
          </p>
        </div>
      </div>
    </div>
  )
}

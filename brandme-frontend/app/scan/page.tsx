import { resolveScanAndFetchPassport } from '@/lib/demoData'
import IntegrityBadge from '@/components/IntegrityBadge'
import FacetList from '@/components/FacetList'
import { Lock, Plus, UserPlus } from 'lucide-react'
import Image from 'next/image'

export default async function ScanPage() {
  const passport = await resolveScanAndFetchPassport()

  if (passport.escalated) {
    return (
      <div className="space-y-8">
        <div className="text-center py-16 space-y-6">
          <div className="flex justify-center">
            <Lock className="w-16 h-16 text-yellow-400" />
          </div>
          <h1 className="text-3xl font-bold">Visibility Under Review</h1>
          <p className="text-gray-400 max-w-md mx-auto">
            This garment passport is currently under human review by our governance team.
            Check back shortly.
          </p>
          <div className="text-sm text-gray-500 font-mono">
            Scan ID: {passport.scan_id}
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-8">
      <div className="relative aspect-[3/4] max-w-2xl mx-auto rounded-xl overflow-hidden bg-gray-900">
        <div className="absolute inset-0 flex items-center justify-center text-gray-600 text-sm">
          [Garment Hero Image]
        </div>
      </div>

      <div className="max-w-2xl mx-auto space-y-6">
        <div>
          <h1 className="text-4xl font-bold mb-2">Atelier 7 / Denim Capsule 03</h1>
          <p className="text-gray-400 text-lg">Reclaimed 14oz selvedge denim</p>
        </div>

        <IntegrityBadge
          status="verified"
          cardanoHash={passport.cardano_tx_hash}
          midnightHash={passport.midnight_tx_hash}
          escalated={false}
        />

        <div className="border-t border-gray-800 pt-6">
          <h2 className="text-xl font-semibold mb-4">Ethics & Sourcing</h2>
          <FacetList facets={passport.facets} />
        </div>

        <div className="flex gap-4 pt-4">
          <button className="flex-1 bg-white text-black py-3 px-6 rounded-lg font-semibold hover:bg-gray-200 transition flex items-center justify-center gap-2">
            <Plus className="w-5 h-5" />
            Add to Stash
          </button>
          <button className="flex-1 border border-gray-700 py-3 px-6 rounded-lg font-semibold hover:bg-gray-900 transition flex items-center justify-center gap-2">
            <UserPlus className="w-5 h-5" />
            Follow Designer
          </button>
        </div>

        <div className="text-xs text-gray-500 space-y-1 pt-4 border-t border-gray-800">
          <p>Request ID: {passport.request_id}</p>
          <p>Region: {passport.region_code}</p>
          <p>Scope: {passport.resolved_scope}</p>
        </div>
      </div>
    </div>
  )
}

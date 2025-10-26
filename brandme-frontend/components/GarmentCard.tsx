import { Shield, CheckCircle, Clock } from 'lucide-react'
import Link from 'next/link'

interface GarmentCardProps {
  imageUrl: string
  title: string
  subtitle: string
  integrityStatus: 'verified' | 'pending'
}

export default function GarmentCard({
  imageUrl,
  title,
  subtitle,
  integrityStatus,
}: GarmentCardProps) {
  return (
    <Link href="/scan">
      <div className="group relative rounded-xl overflow-hidden bg-gray-900 hover:shadow-2xl hover:shadow-white/10 transition-all duration-300 hover:scale-[1.02]">
        <div className="aspect-[3/4] bg-gray-800 relative">
          <div className="absolute inset-0 flex items-center justify-center text-gray-600 text-sm">
            [Image]
          </div>

          <div className="absolute top-3 right-3">
            {integrityStatus === 'verified' ? (
              <div className="bg-green-600 rounded-full p-1.5">
                <CheckCircle className="w-4 h-4 text-white" />
              </div>
            ) : (
              <div className="bg-yellow-600 rounded-full p-1.5">
                <Clock className="w-4 h-4 text-white" />
              </div>
            )}
          </div>
        </div>

        <div className="p-4 space-y-2">
          <h3 className="font-semibold text-lg group-hover:text-gray-300 transition">
            {title}
          </h3>
          <p className="text-sm text-gray-400 line-clamp-2">{subtitle}</p>

          <div className="flex items-center gap-1.5 text-xs text-gray-500 pt-1">
            <Shield className="w-3.5 h-3.5" />
            <span>
              {integrityStatus === 'verified' ? 'Chain verified' : 'Pending verification'}
            </span>
          </div>
        </div>
      </div>
    </Link>
  )
}

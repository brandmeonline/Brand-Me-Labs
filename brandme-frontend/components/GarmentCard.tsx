import { Shield, CheckCircle, Clock } from 'lucide-react'
import Link from 'next/link'

interface GarmentCardProps {
  imageUrl: string
  title: string
  subtitle: string
  integrityStatus: 'verified' | 'pending' | 'demo'
  href?: string
}

export default function GarmentCard({
  imageUrl,
  title,
  subtitle,
  integrityStatus,
  href = '/scan',
}: GarmentCardProps) {
  return (
    <Link href={href}>
      <div className="group relative rounded-xl overflow-hidden bg-gray-900 hover:shadow-2xl hover:shadow-white/10 transition-all duration-300 hover:scale-[1.02]">
        <div className="aspect-[3/4] bg-[#e9e5dd] relative">
          <img
            src={imageUrl}
            alt={title}
            width={600}
            height={800}
            loading="lazy"
            decoding="async"
            className="absolute inset-0 h-full w-full object-contain"
          />

          <div className="absolute top-3 right-3">
            {integrityStatus === 'verified' ? (
              <div className="bg-green-600 rounded-full p-1.5">
                <CheckCircle className="w-4 h-4 text-white" />
              </div>
            ) : integrityStatus === 'pending' ? (
              <div className="bg-yellow-600 rounded-full p-1.5">
                <Clock className="w-4 h-4 text-white" />
              </div>
            ) : (
              <span className="rounded-full bg-gray-900/85 px-3 py-1 text-xs text-white">Demo</span>
            )}
          </div>
        </div>

        <div className="p-4 space-y-2">
          <h3 className="font-semibold text-lg group-hover:text-gray-300 transition">
            {title}
          </h3>
          <p className="text-sm text-gray-400 line-clamp-2">{subtitle}</p>

          <div className="flex items-center gap-1.5 text-xs text-gray-500 pt-1">
            {integrityStatus !== 'demo' && <Shield className="w-3.5 h-3.5" />}
            <span>
              {integrityStatus === 'demo' ? 'Original demo garment' : integrityStatus === 'verified' ? 'Chain verified' : 'Pending verification'}
            </span>
          </div>
        </div>
      </div>
    </Link>
  )
}

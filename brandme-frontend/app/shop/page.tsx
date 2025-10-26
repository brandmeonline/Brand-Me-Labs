import { getDiscoveryFeed } from '@/lib/demoData'
import GarmentCard from '@/components/GarmentCard'

export default async function ShopPage() {
  const feed = await getDiscoveryFeed()

  return (
    <div className="space-y-8">
      <div className="text-center space-y-4 pb-8">
        <h1 className="text-5xl font-bold">Discover</h1>
        <p className="text-gray-400 text-lg">
          Authentic looks. Verified creators. Chain-backed integrity.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {feed.map((item, index) => (
          <GarmentCard
            key={index}
            imageUrl={item.imageUrl}
            title={item.title}
            subtitle={item.subtitle}
            integrityStatus={item.integrityStatus}
          />
        ))}
      </div>
    </div>
  )
}

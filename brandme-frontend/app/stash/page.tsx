import { getMyStash } from '@/lib/demoData'
import GarmentCard from '@/components/GarmentCard'

export default async function StashPage() {
  const stash = await getMyStash()

  return (
    <div className="space-y-8">
      <div className="space-y-4">
        <h1 className="text-5xl font-bold">Your Stash</h1>
        <p className="text-gray-400 text-lg">
          {stash.length} verified item{stash.length !== 1 ? 's' : ''} in your collection
        </p>
      </div>

      {stash.length === 0 ? (
        <div className="text-center py-16 text-gray-500">
          <p className="text-xl">No items in your stash yet.</p>
          <p className="mt-2">Scan garments or discover new drops to get started.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {stash.map((item, index) => (
            <GarmentCard
              key={index}
              imageUrl={item.imageUrl}
              title={item.title}
              subtitle={item.subtitle}
              integrityStatus={item.integrityStatus}
            />
          ))}
        </div>
      )}
    </div>
  )
}

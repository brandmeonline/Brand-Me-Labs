import { AvailabilityState } from '@/components/shell/availability-state'
export default function Page() {
  return (
    <AvailabilityState
      title={'Every piece has a next chapter.'}
      description={
        'Orders are not connected in this preview. No retailer purchase has been made or confirmed.'
      }
    />
  )
}

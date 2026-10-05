import { AvailabilityState } from '@/components/shell/availability-state'
export default function Page() {
  return (
    <AvailabilityState
      title={'A world to discover.'}
      description={
        'The catalog is not connected in this preview. There are no live offers or verified prices to browse yet.'
      }
    />
  )
}

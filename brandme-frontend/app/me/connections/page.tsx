import { AvailabilityState } from '@/components/shell/availability-state'
export default function Page() {
  return (
    <AvailabilityState
      title={'Choose what you let in.'}
      description={
        'No account or provider is connected in this preview. No permissions have been granted.'
      }
    />
  )
}

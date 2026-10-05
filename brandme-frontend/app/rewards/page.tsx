import { AvailabilityState } from '@/components/shell/availability-state'
export default function Page() {
  return (
    <AvailabilityState
      title={'Good contributions matter.'}
      description={
        'Rewards are not connected in this preview. No points or badges have been awarded.'
      }
    />
  )
}

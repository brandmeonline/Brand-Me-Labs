import { AvailabilityState } from '@/components/shell/availability-state'
export default function Page() {
  return (
    <AvailabilityState
      title={'Let’s start with you.'}
      description={
        'Style setup is not available in this preview. You can explore Today without a wallet, camera or account.'
      }
    />
  )
}

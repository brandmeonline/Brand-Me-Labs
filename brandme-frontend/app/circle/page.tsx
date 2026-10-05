import { AvailabilityState } from '@/components/shell/availability-state'
export default function Page() {
  return (
    <AvailabilityState
      title={'Good taste, shared.'}
      description={
        'Circle requests and friend connections are not available in this preview. No invitations have been sent.'
      }
    />
  )
}

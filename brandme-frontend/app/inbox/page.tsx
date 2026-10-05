import { AvailabilityState } from '@/components/shell/availability-state'
export default function Page() {
  return (
    <AvailabilityState
      title={'A little space for what matters.'}
      description={
        'Notifications are not connected in this preview. No messages or friend responses have been fetched.'
      }
    />
  )
}

import { AvailabilityState } from '@/components/shell/availability-state'
export default function Page() {
  return (
    <AvailabilityState
      title={'Your data. Your decisions.'}
      description={
        'Account inspection, export and deletion are not connected in this preview. Display preferences are stored only on this device.'
      }
    />
  )
}

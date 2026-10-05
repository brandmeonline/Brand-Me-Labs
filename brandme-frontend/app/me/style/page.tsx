import { AvailabilityState } from '@/components/shell/availability-state'
export default function Page() {
  return (
    <AvailabilityState
      title={'Your Looking Glass.'}
      description={
        'Style editing is not connected in this preview. No preference changes or inferred profile have been saved.'
      }
    />
  )
}

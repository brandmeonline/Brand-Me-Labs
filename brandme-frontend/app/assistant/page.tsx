import { AvailabilityState } from '@/components/shell/availability-state'
export default function Page() {
  return (
    <AvailabilityState
      title={'A little help, on your terms.'}
      description={
        'Your assistant is not connected in this preview. No tasks, purchases or agent permissions have been created.'
      }
    />
  )
}

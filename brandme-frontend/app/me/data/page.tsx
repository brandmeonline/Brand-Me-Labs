import { PageHeading } from '@/components/shell/page-heading'
import { MyData } from '@/features/privacy/my-data'
export default function Page() {
  return (
    <>
      <PageHeading
        eyebrow="My Data"
        title="Your data. Your decisions."
        description="Inspect the connected inventory, its sources and retention, and the actions currently available."
      />
      <MyData />
    </>
  )
}

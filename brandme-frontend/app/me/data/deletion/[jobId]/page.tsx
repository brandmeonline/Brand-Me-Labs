import { PageHeading } from '@/components/shell/page-heading'
import { DeletionStatus } from '@/features/privacy/my-data'
export default async function Page({
  params,
}: {
  params: Promise<{ jobId: string }>
}) {
  const { jobId } = await params
  return (
    <>
      <PageHeading
        eyebrow="My Data"
        title="Your deletion receipt"
        description="Read the recorded outcome for each category, including retained and non-erasable records."
      />
      <DeletionStatus id={jobId} />
    </>
  )
}

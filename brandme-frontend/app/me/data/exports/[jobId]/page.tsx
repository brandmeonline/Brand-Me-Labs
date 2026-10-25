import { PageHeading } from '@/components/shell/page-heading'
import { DataExport } from '@/features/privacy/my-data'
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
        title="Your requested export"
        description="Check its status and download only the categories you selected."
      />
      <DataExport id={jobId} />
    </>
  )
}

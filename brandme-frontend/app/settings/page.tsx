import type { Metadata } from 'next'
import { PageHeading } from '@/components/shell/page-heading'
import { ExperienceSettings } from '@/components/shell/experience-settings'
export const metadata: Metadata = { title: 'Settings' }
export default function SettingsPage() {
  return (
    <>
      <PageHeading
        eyebrow="Your experience"
        title="Comfort, by design."
        description="A calmer screen, a different light, a simpler view. Make this space yours."
      />
      <section className="bm-settings-panel" aria-label="Display preferences">
        <ExperienceSettings />
      </section>
      <p className="bm-support bm-settings-footer">
        These display choices do not change your style profile or grant access
        to your data.
      </p>
    </>
  )
}

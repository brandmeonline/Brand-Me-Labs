import type { Metadata, Viewport } from 'next'
import './globals.css'
import '@/components/console-shell.css'
import { ConsoleShell } from '@/components/console-shell'
import {
  designTokenCss,
  bodyFont,
  displayFont,
  preferenceBootstrap,
} from '@/lib/shell'
import { ExperiencePreferencesProvider } from '../../brandme-frontend/lib/client/experience-preferences'

export const metadata: Metadata = {
  title: {
    default: 'Brand.Me Operations',
    template: '%s · Brand.Me Operations',
  },
  description: 'Scoped operational workflows for Brand.Me.',
}
export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  viewportFit: 'cover',
}
// Environment and future operator sessions are request-specific, not build-time state.
export const dynamic = 'force-dynamic'
export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const mode = process.env.BRANDME_MODE
  const environment =
    mode && ['demo', 'development', 'sandbox', 'production'].includes(mode)
      ? `${mode} environment`
      : 'Environment not configured'
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <style
          id="brandme-design-tokens"
          dangerouslySetInnerHTML={{ __html: designTokenCss() }}
        />
        <script dangerouslySetInnerHTML={{ __html: preferenceBootstrap }} />
      </head>
      <body className={`${bodyFont.variable} ${displayFont.variable}`}>
        <ExperiencePreferencesProvider>
          <ConsoleShell environment={environment}>{children}</ConsoleShell>
        </ExperiencePreferencesProvider>
      </body>
    </html>
  )
}

import type { Metadata, Viewport } from 'next'
import './globals.css'
import { AppShell } from '@/components/shell/app-shell'
import { ExperiencePreferencesProvider } from '@/lib/client/experience-preferences'
import { preferenceBootstrap } from '@/lib/client/preference-bootstrap'
import { designTokenCss } from '@/lib/design-tokens'
import { bodyFont, displayFont } from '@/lib/fonts'

export const metadata: Metadata = {
  title: { default: 'Brand.Me — Be More U', template: '%s · Brand.Me' },
  description:
    'A wardrobe that feels like you. Shape your style and keep your choices yours.',
}
export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  viewportFit: 'cover',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
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
          <AppShell>{children}</AppShell>
        </ExperiencePreferencesProvider>
      </body>
    </html>
  )
}

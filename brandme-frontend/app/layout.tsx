import type { Metadata } from 'next'
import { Inter } from 'next/font/google'
import './globals.css'
import Header from '@/components/Header'

const inter = Inter({ subsets: ['latin'] })

export const metadata: Metadata = {
  title: 'Brand.Me - Authentic Fashion Identity',
  description: 'Integrity platform for fashion objects',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body className={inter.className}>
        <div className="min-h-screen bg-black text-white">
          <Header />
          <main className="max-w-screen-xl mx-auto p-6 space-y-8">
            {children}
          </main>
        </div>
      </body>
    </html>
  )
}

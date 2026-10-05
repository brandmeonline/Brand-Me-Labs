import localFont from 'next/font/local'
export const bodyFont = localFont({
  src: [
    { path: './fonts/manrope-latin-400-normal.woff2', weight: '400' },
    { path: './fonts/manrope-latin-500-normal.woff2', weight: '500' },
    { path: './fonts/manrope-latin-600-normal.woff2', weight: '600' },
    { path: './fonts/manrope-latin-700-normal.woff2', weight: '700' },
  ],
  variable: '--font-body',
  display: 'swap',
  fallback: ['system-ui', 'sans-serif'],
})
export const displayFont = localFont({
  src: './fonts/cormorant-garamond-latin-500-normal.woff2',
  weight: '500',
  variable: '--font-display',
  display: 'swap',
  fallback: ['Georgia', 'serif'],
})

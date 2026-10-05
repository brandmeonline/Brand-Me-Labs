/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: ['class', '[data-bm-theme="dark"]'],
  content: [
    './app/**/*.{ts,tsx}',
    './components/**/*.{ts,tsx}',
    './features/**/*.{ts,tsx}',
    './lib/**/*.{ts,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        canvas: 'var(--bm-canvas)',
        surface: 'var(--bm-surface)',
        ink: 'var(--bm-ink)',
        forest: 'var(--bm-forest)',
        amber: 'var(--bm-amber)',
        error: 'var(--bm-error)',
        border: 'var(--bm-line)',
        input: 'var(--bm-line)',
        ring: 'var(--bm-accent)',
        background: 'var(--bm-canvas)',
        foreground: 'var(--bm-ink)',
        primary: { DEFAULT: 'var(--bm-ink)', foreground: 'var(--bm-canvas)' },
        secondary: {
          DEFAULT: 'var(--bm-surface)',
          foreground: 'var(--bm-ink)',
        },
        muted: { DEFAULT: 'var(--bm-surface)', foreground: 'var(--bm-muted)' },
        accent: { DEFAULT: 'var(--bm-accent)', foreground: 'var(--bm-canvas)' },
        card: { DEFAULT: 'var(--bm-surface)', foreground: 'var(--bm-ink)' },
        popover: { DEFAULT: 'var(--bm-surface)', foreground: 'var(--bm-ink)' },
        destructive: {
          DEFAULT: 'var(--bm-error)',
          foreground: 'var(--bm-canvas)',
        },
      },
      fontFamily: {
        sans: ['var(--font-body)', 'system-ui', 'sans-serif'],
        display: ['var(--font-display)', 'Georgia', 'serif'],
      },
      borderRadius: {
        control: 'var(--bm-radius-control)',
        image: 'var(--bm-radius-image)',
        sheet: 'var(--bm-radius-sheet)',
      },
    },
  },
  plugins: [require('tailwindcss-animate')],
}

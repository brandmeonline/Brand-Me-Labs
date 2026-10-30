// Dependency-bearing adapters resolve through the console's own package manifest.
export { designTokenCss } from './design-tokens'
export { bodyFont, displayFont } from './fonts'
// This read-only bootstrap string has no framework or package dependencies.
export { preferenceBootstrap } from '../../brandme-frontend/lib/client/preference-bootstrap'
export { consoleNavigation } from './navigation'

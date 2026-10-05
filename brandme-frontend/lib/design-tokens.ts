// Read-only bridge until foundation publishes the design-system export.
import tokens from '../../docs/design/brandme/contracts/design-tokens.json'
export { tokens }
export function designTokenCss(): string {
  const colors = (mode: 'light' | 'dark') =>
    Object.entries(tokens.color)
      .map(([name, value]) => `--bm-${name}:${value[mode]};`)
      .join('')
  return `:root{${colors('light')}color-scheme:light;
    --bm-radius-control:${tokens.radius_px.control}px;--bm-radius-image:${tokens.radius_px.image}px;--bm-radius-sheet:${tokens.radius_px.sheet}px;
    --bm-target:${tokens.layout.target_min_px}px;--bm-nav-height:${tokens.layout.bottom_nav_px}px;
    --bm-ease:cubic-bezier(${tokens.motion.easing.join(',')});--bm-button-duration:${tokens.motion.button_ms}ms;--bm-sheet-duration:${tokens.motion.sheet_ms}ms;--bm-route-duration:${tokens.motion.route_ms[0]}ms;
    --bm-z-sticky:${tokens.z_index.sticky};--bm-z-panel:${tokens.z_index.panel};--bm-z-modal:${tokens.z_index.modal};--bm-z-critical:${tokens.z_index.critical};}
    :root[data-bm-theme="dark"]{${colors('dark')}color-scheme:dark;}
    @media(prefers-color-scheme:dark){:root:not([data-bm-theme="light"]){${colors('dark')}color-scheme:dark;}}`
}

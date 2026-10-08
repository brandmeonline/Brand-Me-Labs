import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { tokens, contrastRatio } from '../src/index.ts';

const spec = JSON.parse(readFileSync(new URL('../../../docs/design/brandme/contracts/design-tokens.json', import.meta.url), 'utf8'));

test('generated tokens equal the design contract exactly', () => {
  assert.deepEqual(JSON.parse(JSON.stringify(tokens)), spec);
});

test('every colour token is emitted for light and dark', () => {
  const css = readFileSync(new URL('../generated/tokens.css', import.meta.url), 'utf8');
  for (const [name, v] of Object.entries(spec.color) as [string, { light: string; dark: string }][]) {
    const varName = `--bm-color-${name.replace(/_/g, '-')}`;
    assert.ok(css.includes(`${varName}: ${v.light};`), `${varName} light`);
    assert.ok(css.includes(`${varName}: ${v.dark};`), `${varName} dark`);
  }
  assert.match(css, /prefers-reduced-motion: reduce/);
  assert.match(css, /prefers-color-scheme: dark/);
});

// Text pairings the UI will use. WCAG AA: 4.5 body text, 3.0 large text / UI.
const TEXT_PAIRS: [string, string, number][] = [
  ['ink', 'canvas', 4.5], ['ink', 'surface', 4.5],
  ['muted', 'canvas', 4.5], ['muted', 'surface', 4.5],
  ['accent', 'canvas', 4.5], ['accent', 'surface', 4.5],
  ['forest', 'surface', 4.5], ['amber', 'surface', 4.5], ['error', 'surface', 4.5],
];

for (const scheme of ['light', 'dark'] as const) {
  for (const [fg, bg, min] of TEXT_PAIRS) {
    test(`${scheme}: ${fg} on ${bg} ≥ ${min}`, () => {
      const ratio = contrastRatio(spec.color[fg][scheme], spec.color[bg][scheme]);
      assert.ok(ratio >= min, `${fg}/${bg} ${scheme} = ${ratio.toFixed(2)}`);
    });
  }
}

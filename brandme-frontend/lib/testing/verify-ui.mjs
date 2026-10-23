/**
 * Component behavior in JSDOM, not browser/visual/device evidence.
 * Node 24 + validation-only typescript@5.3.3, jsdom@26.1.0,
 * @testing-library/{react@16.1.0,dom@10.4.0,user-event@14.6.1}.
 * Set BRANDME_TEST_PACKAGE_JSON to the validation dependency package.json.
 */
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
import { afterEach, test } from 'node:test'

const require = createRequire(
  process.env.BRANDME_TEST_PACKAGE_JSON ||
    new URL('../../package.json', import.meta.url),
)
const ts = require('typescript')
const { JSDOM } = require('jsdom')
const dom = new JSDOM('<!doctype html><html><body></body></html>', {
  url: 'http://localhost',
})
for (const name of [
  'window',
  'self',
  'document',
  'navigator',
  'HTMLElement',
  'HTMLInputElement',
  'Element',
  'Node',
  'NodeFilter',
  'MutationObserver',
  'Event',
  'CustomEvent',
  'KeyboardEvent',
  'MouseEvent',
  'getComputedStyle',
]) {
  Object.defineProperty(globalThis, name, {
    configurable: true,
    value:
      name === 'getComputedStyle'
        ? dom.window.getComputedStyle.bind(dom.window)
        : dom.window[name],
  })
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true
// Compile app TSX with the same automatic JSX runtime as Next, without modifying app config.
const compile = (module, filename) =>
  module._compile(
    ts.transpileModule(readFileSync(filename, 'utf8'), {
      compilerOptions: {
        module: ts.ModuleKind.CommonJS,
        target: ts.ScriptTarget.ES2020,
        jsx: ts.JsxEmit.ReactJSX,
        esModuleInterop: true,
      },
      fileName: filename,
    }).outputText,
    filename,
  )
require.extensions['.ts'] = compile
require.extensions['.tsx'] = compile
const source = (relative) =>
  require(fileURLToPath(new URL(relative, import.meta.url)))
const React = require('react')
const {
  render,
  screen,
  cleanup,
  fireEvent,
  act,
} = require('@testing-library/react')
const userEvent = require('@testing-library/user-event').default
const h = React.createElement
const { Button, ActionLink } = source('../../components/ui/button.tsx')
const { Input, Select, Switch } = source('../../components/ui/field.tsx')
const { Slider } = source('../../components/ui/slider.tsx')
const { Tabs } = source('../../components/ui/tabs.tsx')
const { Dialog, Drawer } = source('../../components/ui/dialog.tsx')
const { Toast } = source('../../components/ui/feedback.tsx')
const { EvidenceLabel } = source('../../components/ui/evidence-label.tsx')
const { Price } = source('../../components/ui/price.tsx')
const { formatMoney } = source('../money.ts')
const { useNavigationClearance } = source(
  '../client/use-navigation-clearance.ts',
)
afterEach(() => {
  cleanup()
  document.documentElement.removeAttribute('style')
})

test('money retains every digit and respects 0/2/3-decimal currencies', () => {
  assert.equal(
    formatMoney({ amount_minor: '9612', currency: 'USD' }),
    'USD 96.12',
  )
  assert.equal(formatMoney({ amount_minor: '0', currency: 'USD' }), 'USD 0.00')
  assert.equal(
    formatMoney({ amount_minor: '1234', currency: 'JPY' }),
    'JPY 1,234',
  )
  assert.equal(
    formatMoney({ amount_minor: '1234', currency: 'KWD' }),
    'KWD 1.234',
  )
  assert.equal(
    formatMoney({ amount_minor: '999999999999999999', currency: 'USD' }),
    'USD 9,999,999,999,999,999.99',
  )
  assert.equal(
    formatMoney({ amount_minor: '999999999999999999', currency: 'JPY' }),
    'JPY 999,999,999,999,999,999',
  )
})
test('invalid money never becomes an estimated or rounded price', () => {
  for (const amount_minor of [
    96.12,
    '-1',
    '01',
    '1.5',
    'NaN',
    '1e5',
    '1000000000000000000',
  ]) {
    assert.throws(() => formatMoney({ amount_minor, currency: 'USD' }))
  }
  for (const currency of ['ZZZ', 'XXX', 'XTS', 'usd', '', 'USDD'])
    assert.throws(() => formatMoney({ amount_minor: '1', currency }))
  render(h(Price, { money: { amount_minor: '1.5', currency: 'USD' } }))
  assert.ok(screen.getByText('Price unavailable'))
})
test('missing currency metadata fails closed', () => {
  const original = Intl.supportedValuesOf
  try {
    Intl.supportedValuesOf = undefined
    assert.throws(() => formatMoney({ amount_minor: '100', currency: 'USD' }))
  } finally {
    Intl.supportedValuesOf = original
  }
})
test('buttons default to non-submit and cannot invoke pending actions; links retain navigation semantics', async () => {
  let calls = 0
  const user = userEvent.setup()
  render(
    h(
      'div',
      null,
      h(
        Button,
        { onClick: () => calls++, pending: true, pendingLabel: 'Saving' },
        'Save',
      ),
      h(ActionLink, { href: '/settings' }, 'Settings'),
    ),
  )
  const button = screen.getByRole('button', { name: 'Saving' })
  assert.equal(button.type, 'button')
  assert.equal(button.getAttribute('aria-busy'), 'true')
  await user.click(button)
  assert.equal(calls, 0)
  assert.equal(
    screen.getByRole('link', { name: 'Settings' }).getAttribute('href'),
    '/settings',
  )
})
test('fields have stable labels, associated help/errors, and distinct ids', () => {
  render(
    h(
      'div',
      null,
      h(Input, {
        label: 'Name',
        description: 'Keep it editable.',
        error: 'Please enter a name.',
      }),
      h(Input, { label: 'Other name' }),
      h(Select, { label: 'Occasion' }, h('option', { value: 'work' }, 'Work')),
    ),
  )
  const input = screen.getByRole('textbox', { name: 'Name', exact: true })
  assert.notEqual(
    input.id,
    screen.getByRole('textbox', { name: 'Other name' }).id,
  )
  assert.equal(input.getAttribute('aria-invalid'), 'true')
  for (const id of input.getAttribute('aria-describedby').split(' '))
    assert.ok(document.getElementById(id))
  assert.equal(screen.getByRole('combobox', { name: 'Occasion' }).value, 'work')
})
test('switch supports keyboard toggle and has separate label and description', async () => {
  function Example() {
    const [checked, setChecked] = React.useState(false)
    return h(Switch, {
      label: 'Reduce motion',
      description: 'Skip flights.',
      checked,
      onCheckedChange: setChecked,
    })
  }
  const user = userEvent.setup()
  render(h(Example))
  const control = screen.getByRole('switch', {
    name: 'Reduce motion',
    exact: true,
  })
  control.focus()
  await user.keyboard(' ')
  assert.equal(control.checked, true)
  assert.equal(
    document.getElementById(control.getAttribute('aria-describedby'))
      .textContent,
    'Skip flights.',
  )
})
test('slider distinguishes unknown, uses five-point keys, accepts integer entry, rejects fractional draft, and clears', async () => {
  let observed = null
  function Example() {
    const [value, setValue] = React.useState(null)
    return h(Slider, {
      label: 'Expression',
      leftLabel: 'Understated',
      rightLabel: 'Expressive',
      value,
      onValueChange: (next) => {
        observed = next
        setValue(next)
      },
    })
  }
  const user = userEvent.setup()
  render(h(Example))
  const slider = screen.getByRole('slider', { name: 'Expression' })
  const number = screen.getByRole('spinbutton', { name: 'Expression value' })
  assert.match(slider.getAttribute('aria-valuetext'), /Not set/)
  assert.equal(number.value, '')
  slider.focus()
  await user.keyboard('{ArrowRight}')
  assert.equal(observed, 55)
  await user.keyboard('{Home}{ArrowLeft}')
  assert.equal(observed, 0)
  await user.keyboard('{End}{ArrowRight}')
  assert.equal(observed, 100)
  fireEvent.change(number, { target: { value: '72' } })
  assert.equal(observed, 72)
  fireEvent.change(number, { target: { value: '72.5' } })
  assert.equal(observed, 72)
  assert.equal(number.getAttribute('aria-invalid'), 'true')
  fireEvent.change(number, { target: { value: '101' } })
  assert.equal(observed, 72)
  await user.click(screen.getByRole('button', { name: 'Clear expression' }))
  assert.equal(observed, null)
  assert.match(slider.getAttribute('aria-valuetext'), /Not set/)
})
test('tabs use one tab stop, skip disabled tabs, wrap and support Home/End', async () => {
  function Example() {
    const [value, setValue] = React.useState('one')
    return h(Tabs, {
      label: 'Records',
      value,
      onValueChange: setValue,
      items: [
        { id: 'one', label: 'Declared', content: 'Your choice' },
        {
          id: 'missing',
          label: 'Unavailable',
          disabled: true,
          content: 'No service',
        },
        { id: 'two', label: 'Inferred', content: 'No inference' },
      ],
    })
  }
  const user = userEvent.setup()
  render(h(Example))
  const first = screen.getByRole('tab', { name: 'Declared' })
  first.focus()
  await user.keyboard('{ArrowRight}')
  assert.equal(
    document.activeElement,
    screen.getByRole('tab', { name: 'Inferred' }),
  )
  assert.equal(screen.getByRole('tabpanel').textContent, 'No inference')
  assert.equal(
    screen.getAllByRole('tab').filter((tab) => tab.tabIndex === 0).length,
    1,
  )
  await user.keyboard('{ArrowRight}')
  assert.equal(document.activeElement, first)
  await user.keyboard('{End}')
  assert.equal(
    document.activeElement,
    screen.getByRole('tab', { name: 'Inferred' }),
  )
  await user.keyboard('{Home}')
  assert.equal(document.activeElement, first)
})
for (const [name, Component] of [
  ['dialog', Dialog],
  ['drawer', Drawer],
]) {
  test(`${name} opens, contains keyboard focus, closes on Escape, and restores trigger`, async () => {
    const user = userEvent.setup()
    render(
      h(
        Component,
        {
          title: 'Example',
          description: 'Only a demonstration.',
          trigger: h(Button, null, 'Open'),
        },
        h(Input, { label: 'Note' }),
      ),
    )
    const trigger = screen.getByRole('button', { name: 'Open', exact: true })
    await user.click(trigger)
    const panel = screen.getByRole('dialog', { name: 'Example' })
    assert.equal(
      document.getElementById(panel.getAttribute('aria-describedby'))
        .textContent,
      'Only a demonstration.',
    )
    for (let i = 0; i < 12; i++) {
      await user.tab()
      assert.ok(panel.contains(document.activeElement))
    }
    await user.keyboard('{Escape}')
    assert.equal(screen.queryByRole('dialog'), null)
    assert.equal(document.activeElement, trigger)
  })
}
test('generative preview cannot become a fit label; missing fit method/limits fail closed', () => {
  const view = render(h(EvidenceLabel, { kind: 'generative_preview' }))
  assert.ok(screen.getByText('Generative preview'))
  assert.match(view.container.textContent, /not a sizing or fit assessment/)
  assert.equal(screen.queryByText('Fit estimate', { exact: true }), null)
  view.rerender(
    h(EvidenceLabel, { kind: 'calibrated_fit', method: '', limits: '' }),
  )
  assert.match(view.container.textContent, /unavailable/)
})
test('toast keeps its live region mounted and does not steal focus', () => {
  const view = render(h(Toast, { message: null }))
  const region = screen.getByRole('status')
  const focus = document.activeElement
  view.rerender(h(Toast, { message: 'Example complete' }))
  assert.equal(screen.getByRole('status'), region)
  assert.equal(region.textContent, 'Example complete')
  assert.equal(document.activeElement, focus)
})
test('navigation clearance measures growth, clears public routes, and disconnects on unmount', () => {
  let resized
  let disconnected = 0
  const originalObserver = globalThis.ResizeObserver
  globalThis.ResizeObserver = class {
    constructor(callback) {
      resized = callback
    }
    observe() {}
    disconnect() {
      disconnected++
    }
  }
  function Example({ publicPage }) {
    const ref = React.useRef(null)
    useNavigationClearance(ref, publicPage)
    return publicPage
      ? null
      : h('nav', { ref, 'aria-label': 'Example navigation' })
  }
  try {
    const view = render(h(Example, { publicPage: false }))
    const nav = screen.getByRole('navigation')
    nav.getBoundingClientRect = () => ({ height: 116.2 })
    act(() => resized())
    assert.equal(
      document.documentElement.style.getPropertyValue('--bm-nav-occupied'),
      '117px',
    )
    view.rerender(h(Example, { publicPage: true }))
    assert.equal(
      document.documentElement.style.getPropertyValue('--bm-nav-occupied'),
      '0px',
    )
    view.unmount()
    assert.equal(
      document.documentElement.style.getPropertyValue('--bm-nav-occupied'),
      '',
    )
    assert.equal(disconnected, 2)
  } finally {
    globalThis.ResizeObserver = originalObserver
  }
})

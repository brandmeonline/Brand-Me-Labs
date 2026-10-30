/**
 * Component behavior in JSDOM, not browser/visual/device evidence.
 * Node 24 + validation-only typescript@5.3.3, jsdom@26.1.0,
 * @testing-library/{react@16.1.0,dom@10.4.0,user-event@14.6.1}.
 * Set BRANDME_TEST_PACKAGE_JSON to the validation dependency package.json.
 */
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createRequire, Module } from 'node:module'
import { fileURLToPath } from 'node:url'
import { afterEach, test } from 'node:test'
import { registerHapticsTests } from './verify-haptics.mjs'

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
  'addEventListener',
  'removeEventListener',
]) {
  Object.defineProperty(globalThis, name, {
    configurable: true,
    value:
      ['getComputedStyle', 'addEventListener', 'removeEventListener'].includes(name)
        ? dom.window[name].bind(dom.window)
        : dom.window[name],
  })
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true
// Compile app TSX with the same automatic JSX runtime as Next, without modifying app config.
const compile = (module, filename) => {
  // Keep each app's @/* aliases local when both React runtimes share this runner.
  const consoleRoot = new URL('../../../brandme-console/', import.meta.url)
  const aliasRoot = filename.startsWith(fileURLToPath(consoleRoot))
    ? consoleRoot
    : new URL('../../', import.meta.url)
  const moduleRequire = module.require.bind(module)
  module.require = (specifier) => moduleRequire(
    specifier.startsWith('@/')
      ? fileURLToPath(new URL(specifier.slice(2), aliasRoot))
      : specifier,
  )
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
}
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
const { formatMoney, parseMoneyInput, moneyInputValue } = source('../money.ts')
const { validateGuest, guestPayload } = source('../../features/persona/guest-draft.ts')
const {ExperiencePreferencesProvider,useExperiencePreferences}=source('../client/experience-preferences.tsx')
const { useNavigationClearance } = source(
  '../client/use-navigation-clearance.ts',
)
const { primaryNavigation, secondaryNavigation, isActiveRoute } = source('../../components/shell/navigation.tsx')
const { SocialHorizon } = source('../../features/social/horizons.tsx')
const { Wordmark } = source('../../components/shell/wordmark.tsx')
const { AppShell } = source('../../components/shell/app-shell.tsx')
const { PathnameContext } = require('next/dist/shared/lib/hooks-client-context.shared-runtime')
afterEach(() => {
  cleanup()
  document.documentElement.removeAttribute('style')
})
registerHapticsTests({ source, React, render, cleanup, act })

test('three rooms retain secondary destinations and legacy decision/product context', () => {
  assert.deepEqual(primaryNavigation.map(item => item.label), ['Shops', 'Social', 'Closet'])
  const reachable = new Set([...primaryNavigation, ...secondaryNavigation].map(item => item.href))
  for (const href of ['/today', '/style', '/circle', '/me', '/discover', '/assistant', '/rewards', '/orders', '/inbox', '/me/data', '/me/connections', '/settings']) assert.ok(reachable.has(href), href)
  assert.ok(isActiveRoute('/circle/decisions/example', '/social'))
  assert.ok(isActiveRoute('/products/provider:item', '/discover'))
  assert.equal(isActiveRoute('/socially', '/social'), false)
  render(h(Wordmark))
  assert.equal(screen.getByRole('link', { name: 'Brand.Me home' }).getAttribute('href'), '/social/flow')
})

test('shell menu marks one closest destination while retaining room context across nested routes', async () => {
  const originalMedia = globalThis.matchMedia
  globalThis.matchMedia = () => ({ matches: false, addEventListener() {}, removeEventListener() {} })
  const user = userEvent.setup()
  const shell = (path) => h(PathnameContext.Provider, { value: path },
    h(ExperiencePreferencesProvider, null, h(AppShell, null, h('h1', null, 'Route content'))))
  const currentHref = (navigation) => {
    const current = navigation.querySelectorAll('[aria-current="page"]')
    assert.equal(current.length, 1)
    return current[0].getAttribute('href')
  }
  try {
    const view = render(shell('/circle/decisions/example'))
    assert.equal(currentHref(screen.getByRole('navigation', { name: 'Primary', exact: true })), '/social')
    assert.equal(currentHref(screen.getByRole('navigation', { name: 'Explore', exact: true })), '/circle')
    assert.equal(view.container.querySelector('.bm-breadcrumb strong').textContent, 'My circle')
    await user.click(screen.getByRole('button', { name: 'Open menu' }))
    let menu = screen.getByRole('navigation', { name: 'Menu navigation' })
    assert.equal(currentHref(menu), '/circle')
    assert.equal(menu.querySelector('a[href="/social"]').getAttribute('data-active'), 'true')
    assert.equal(menu.querySelector('a[href="/social"]').getAttribute('aria-current'), null)

    // Exercise the sheet link; the pathname provider supplies the router transition.
    const dataLink = menu.querySelector('a[href="/me/data"]')
    dataLink.addEventListener('click', event => event.preventDefault(), { once: true })
    await user.click(dataLink)
    assert.equal(screen.queryByRole('dialog', { name: 'Your space' }), null)
    view.rerender(shell('/me/data'))
    assert.equal(view.container.querySelector('.bm-breadcrumb strong').textContent, 'My Data')
    assert.equal(currentHref(screen.getByRole('navigation', { name: 'Explore', exact: true })), '/me/data')
    assert.equal(document.activeElement, screen.getByRole('main'))
    await user.click(screen.getByRole('button', { name: 'Open menu' }))
    menu = screen.getByRole('navigation', { name: 'Menu navigation' })
    assert.equal(currentHref(menu), '/me/data')
    assert.equal(menu.querySelector('a[href="/me"]').getAttribute('aria-current'), null)
    assert.equal(menu.querySelector('a[href="/me"]').getAttribute('data-active'), null)
    await user.keyboard('{Escape}')
    assert.equal(screen.queryByRole('dialog', { name: 'Your space' }), null)
    assert.equal(document.activeElement, screen.getByRole('button', { name: 'Open menu' }))
  } finally {
    cleanup()
    globalThis.matchMedia = originalMedia
  }
})

test('unavailable horizons remain navigable and contain no synthetic feed cards or prices', () => {
  for (const active of ['flow', 'editorial']) {
    const view = render(h(SocialHorizon, { active }))
    const navigation = screen.getByRole('navigation', { name: 'Social horizons' })
    assert.equal(navigation.querySelectorAll('[aria-current="page"]').length, 1)
    assert.equal(navigation.querySelector('[aria-current="page"]').getAttribute('href'), `/social/${active}`)
    assert.match(view.container.textContent, /not available in this preview/i)
    assert.ok(screen.getByRole('complementary', { name: 'Brands & designers' }))
    assert.equal(view.container.querySelectorAll('article, img, .bm-price').length, 0)
    assert.equal(screen.getByRole('link', { name: 'See decisions in Now' }).getAttribute('href'), '/social/now')
    view.unmount()
  }
})

test('budget entry preserves exact decimal amounts and rejects rounded inputs',()=>{
  for(const [value,currency,minor]of [['150.00','USD','15000'],['150','JPY','150'],['1.234','KWD','1234'],['9999999999999999.99','USD','999999999999999999']]){
    assert.equal(parseMoneyInput(value,currency),minor);assert.equal(parseMoneyInput(moneyInputValue(minor,currency),currency),minor)
  }
  assert.equal(parseMoneyInput('','USD'),null)
  for(const [value,currency]of [['1.234','USD'],['1.1','JPY'],['1e9','USD'],['-5','USD'],['1','ZZZ']])assert.throws(()=>parseMoneyInput(value,currency))
})
test('corrupt guest records cannot introduce invalid axes, looks or implicit learning',()=>{
  const valid={id:'guest-test-namespace-123',step:3,intent:'everyday',looks:[0],room:'walnut_atelier',expression:25,color:null,fit_language:25,learning:false,saved:true}
  assert.deepEqual(validateGuest(valid),valid)
  for(const patch of [{looks:[20]},{looks:[0,0]},{learning:'yes'},{saved:null},{expression:101},{color:NaN},{room:'missing'},{intent:null},{step:4}])assert.equal(validateGuest({...valid,...patch}),null)
  assert.deepEqual(guestPayload(valid).persona.declared.color,{value:null,locked:false})
  assert.equal(guestPayload(valid).persona.learning_enabled,false)
})

test('rapid preference changes compose and survive a fresh provider mount',async()=>{
  const originalMedia=globalThis.matchMedia,originalStorage=globalThis.localStorage
  Object.defineProperty(globalThis,'localStorage',{configurable:true,value:dom.window.localStorage})
  globalThis.matchMedia=()=>({matches:false,addEventListener(){},removeEventListener(){}})
  localStorage.clear()
  function Controls(){const {preferences,update,ready}=useExperiencePreferences();return h('button',{disabled:!ready,onClick:()=>{update({theme:'dark'});update({motion:'reduce'});update({simpleView:true})}},`${preferences.theme}/${preferences.motion}/${preferences.simpleView}`)}
  try{
    const view=render(h(ExperiencePreferencesProvider,null,h(Controls)))
    await userEvent.setup().click(screen.getByRole('button',{name:'system/system/false'}))
    assert.ok(screen.getByRole('button',{name:'dark/reduce/true'}))
    assert.deepEqual(JSON.parse(localStorage.getItem('brandme:experience:v1')),{theme:'dark',motion:'reduce',simpleView:true,highContrast:false})
    view.unmount();render(h(ExperiencePreferencesProvider,null,h(Controls)))
    assert.ok(screen.getByRole('button',{name:'dark/reduce/true'}))
  }finally{cleanup();globalThis.matchMedia=originalMedia;Object.defineProperty(globalThis,'localStorage',{configurable:true,value:originalStorage})}
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

// Use the console's own React runtime: the consumer uses React 19 and the
// console uses React 18. Routing is the only framework behavior replaced here.
const consoleRequire = createRequire(
  new URL('../../../brandme-console/package.json', import.meta.url),
)
const consoleReact = consoleRequire('react')
const renderConsole = consoleRequire('react-dom/server').renderToStaticMarkup
const consoleSource = (path) => source(`../../../brandme-console/${path}`)
const {
  CONSOLE_SHELL_CONTRACT: consoleContract,
  ConsolePageHeader,
} = consoleSource('components/console-contract.ts')
const { isLegacyConsolePath } = consoleSource('lib/console-contract.ts')
const { ExperiencePreferencesProvider: ConsolePreferences } = consoleSource(
  'lib/client/experience-preferences.tsx',
)
const consoleElement = consoleReact.createElement
function renderConsoleShell(pathname, children) {
  const filename = fileURLToPath(
    new URL('../../../brandme-console/components/console-shell.tsx', import.meta.url),
  )
  const shellModule = new Module(filename)
  shellModule.filename = filename
  const shellRequire = createRequire(filename)
  shellModule.require = (request) => {
    if (request === 'next/navigation') return { usePathname: () => pathname }
    if (request.startsWith('@/')) return consoleSource(request.slice(2))
    return shellRequire(request)
  }
  compile(shellModule, filename)
  return renderConsole(consoleElement(
    ConsolePreferences,
    null,
    consoleElement(shellModule.exports.ConsoleShell, { environment: 'development environment' }, children),
  ))
}

test('console patch contract preserves public exports, reserved routes and header imports', () => {
  const publicEntry = consoleSource('components/console-contract.ts')
  assert.deepEqual(Object.keys(publicEntry).sort(), ['CONSOLE_SHELL_CONTRACT', 'ConsolePageHeader'])
  assert.equal(ConsolePageHeader, consoleSource('components/console-page-header.tsx').ConsolePageHeader)
  assert.equal(consoleContract.version, '1.1.1')
  assert.equal(consoleContract.mainId, 'console-content')
  assert.equal(consoleContract.pageRoot, 'app/(ops)')
  assert.equal(consoleContract.headerClass, 'console-page-header')
  assert.equal(consoleContract.tableClass, 'console-table-region')
  assert.deepEqual(consoleContract.navigation.map(({ href }) => href), [
    '/', '/providers', '/ingestion', '/commerce/operations', '/chain/operations',
    '/rights/issuers', '/manufacturing/jobs', '/moderation', '/rewards-disputes', '/capabilities',
  ])
  assert.deepEqual(consoleContract.legacyRoots, ['/dashboard', '/proof'])
})

test('console public header preserves optional slots and owns only the page heading', () => {
  const title = 'Provider <review> & approval'
  const document = new JSDOM(renderConsole(consoleElement(ConsolePageHeader, {
    eyebrow: 'Operations',
    title,
    description: 'Authorized records only.',
    actions: consoleElement('a', { href: '/providers/new' }, 'Add provider'),
  }))).window.document
  assert.equal(document.querySelectorAll('h1').length, 1)
  assert.equal(document.querySelector('h1').textContent, title)
  assert.equal(document.querySelector('header').className, consoleContract.headerClass)
  assert.equal(document.querySelector('.console-eyebrow').textContent, 'Operations')
  assert.equal(document.querySelector('.console-page-actions a').getAttribute('href'), '/providers/new')
  assert.equal(document.querySelectorAll('main, nav').length, 0)
  const minimal = new JSDOM(renderConsole(consoleElement(ConsolePageHeader, { title }))).window.document
  assert.equal(minimal.querySelectorAll('h1').length, 1)
  assert.equal(minimal.querySelector('.console-eyebrow, .console-page-actions, p'), null)
})

test('console shell owns one focusable main and skip target around a domain header', () => {
  const document = new JSDOM(renderConsoleShell('/providers/example/setup',
    consoleElement('section', null, consoleElement(ConsolePageHeader, { title: 'Provider setup' })),
  )).window.document
  assert.equal(document.querySelectorAll('main').length, 1)
  const main = document.querySelector('main')
  assert.equal(main.id, consoleContract.mainId)
  assert.equal(main.getAttribute('tabindex'), '-1')
  assert.equal(document.querySelector('.console-skip').getAttribute('href'), `#${main.id}`)
  assert.equal(main.querySelectorAll('h1').length, 1)
  assert.equal(main.querySelector('nav'), null)
  assert.equal(document.querySelector('nav[aria-label="Operations"] [aria-current="page"]').getAttribute('href'), '/providers')
})

test('console legacy roots pass through without duplicate landmarks or prefix collisions', () => {
  const legacyPage = consoleElement('main', { id: 'legacy-content' },
    consoleElement('h1', null, 'Existing surface'),
  )
  for (const pathname of ['/dashboard', '/dashboard/scans', '/proof', '/proof/scan-123']) {
    assert.equal(isLegacyConsolePath(pathname), true, pathname)
    assert.equal(renderConsoleShell(pathname, legacyPage), renderConsole(legacyPage), pathname)
  }
  for (const pathname of ['/', '/providers', '/dashboard-archive', '/proofing']) {
    assert.equal(isLegacyConsolePath(pathname), false, pathname)
  }
})

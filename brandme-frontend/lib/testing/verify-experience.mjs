/** Preview behavior with explicit HTTP doubles. Never live-feed or human visual approval evidence. */
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { mkdir, writeFile } from 'node:fs/promises'
import path from 'node:path'
const require = createRequire(new URL('../../package.json', import.meta.url))
const { chromium } = require('playwright')
const AxeBuilder = require('@axe-core/playwright').default
const base = process.env.BRANDME_CONSUMER_URL || 'http://127.0.0.1:3000'
const evidence = process.env.BRANDME_EVIDENCE_DIR
if (!evidence || !['localhost', '127.0.0.1'].includes(new URL(base).hostname)) throw new Error('Local UI test runner required')
const output = path.join(evidence, 'experience-preview')
await mkdir(output, { recursive: true })
const owner = '12345678-1234-4234-8234-123456789012'
const other = '22345678-1234-4234-8234-123456789012'
const decision = '32345678-1234-4234-8234-123456789012'
const browser = await chromium.launch({ headless: true })
const results = []
try {
  for (const width of [320, 390, 768, 1440]) {
    const context = await browser.newContext({ viewport: { width, height: 900 }, reducedMotion: 'reduce' })
    try {
      let identity = 'guest', memberId = owner, revision = '1'
      const requests = []
      await context.route('**/api/v1/**', async route => {
        const request = route.request(), url = new URL(request.url())
        const p = url.pathname.replace('/api/v1', '')
        requests.push({ path: p, method: request.method(), search: url.search })
        const reply = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
        if (p === '/me') {
          if (identity === 'guest') return reply({ code: 'unauthenticated', title: 'Sign in' }, 401)
          if (identity === 'unavailable') return reply({ code: 'gateway_unavailable', title: 'Unavailable' }, 503)
          return reply({ member: { id: memberId, display_name: memberId === owner ? 'Aster Test' : 'Birch Test', handle: 'test-only' } })
        }
        if (p === '/me/persona') return reply({ profile: { member_id: memberId, version: revision }, axes: [
          { axis: 'expression', declared: Number(revision) === 1 ? 72 : 24, inferred: null, effective: 72, hidden: false, locked: true },
          { axis: 'temperature', declared: 81, inferred: 63, effective: 81, hidden: true, locked: true },
        ] })
        if (p === '/rewards') return reply({ badges: [
          { badge_id: 'earned', title: 'Test contribution', criteria: 'Explicit HTTP test double.', earned: true },
          { badge_id: 'unearned', title: 'Unearned test badge', criteria: 'Not earned.', earned: false },
        ] })
        if (p === '/wardrobe/items') return reply({ items: [
          { id: 'own-item', member_id: memberId, title: memberId === owner ? 'Aster saved jacket' : 'Birch saved coat', collection: 'owned' },
          { id: 'other-item', member_id: 'different-member', title: 'Wrong owner item', collection: 'owned' },
        ] })
        if (p === '/decisions') return reply({ items: [{ decision_id: decision, prompt: url.searchParams.get('role') === 'mine' ? 'My test request' : 'A friend asks about this look', state: 'open', response_count: 2 }], next_cursor: null })
        return reply({ code: 'unexpected_test_request', title: 'This test does not provide that service' }, 503)
      })
      const page = await context.newPage(), errors = []
      page.on('pageerror', error => errors.push(error.message))
      async function waitForNavigationMeasurement() {
        await page.waitForFunction(() => {
          const bar = document.querySelector('.bm-bottom-nav')
          const measured = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--bm-nav-occupied'))
          return bar && Math.abs(measured - Math.ceil(bar.getBoundingClientRect().height)) <= 1
        })
      }
      async function inspectMobileScroll(name, theme) {
        if (width > 768) return
        for (const scale of [100, 200]) {
          await page.evaluate(scale => { document.documentElement.style.fontSize = `${scale}%` }, scale)
          await page.evaluate(() => document.fonts.ready)
          await waitForNavigationMeasurement()
          const section = page.locator(name === 'private-persona' ? '#card-badges' : '#brand-stream-heading')
          await section.evaluate(element => {
            element.scrollIntoView({ block: 'start' })
            window.scrollBy(0, -32)
          })
          const middle = await section.evaluate(element => ({
            top: element.getBoundingClientRect().top,
            bottom: element.getBoundingClientRect().bottom,
            navigation: document.querySelector('.bm-bottom-nav').getBoundingClientRect().top,
          }))
          assert(middle.top >= 0 && middle.bottom <= middle.navigation, `${name}/${width}/${scale}% midsection heading obscured`)
          await page.screenshot({ path: path.join(output, `${name}-${width}-${theme}-midsection-${scale}.png`), fullPage: false, animations: 'disabled' })
          const last = page.locator('main :is(a, button, input, select, textarea):visible:not(:disabled)').last()
          await last.focus()
          await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight))
          await last.evaluate(element => element.scrollIntoView({ block: 'nearest' }))
          const bounds = await last.evaluate(element => ({
            top: element.getBoundingClientRect().top,
            bottom: element.getBoundingClientRect().bottom,
            content: document.querySelector('.bm-route-content').getBoundingClientRect().bottom,
            navigation: document.querySelector('.bm-bottom-nav').getBoundingClientRect().top,
          }))
          assert(bounds.top >= 0 && bounds.bottom <= bounds.navigation - 8, `${name}/${width}/${scale}% final control obscured: ${JSON.stringify(bounds)}`)
          assert(bounds.content <= bounds.navigation - 16, `${name}/${width}/${scale}% page end obscured: ${JSON.stringify(bounds)}`)
          assert(await last.evaluate(element => element === document.activeElement), 'Final control keeps keyboard focus')
          assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `${name}/${width}/${scale}% horizontal overflow`)
          await page.screenshot({ path: path.join(output, `${name}-${width}-${theme}-end-${scale}.png`), fullPage: false, animations: 'disabled' })
        }
        await page.evaluate(() => { document.documentElement.style.removeProperty('font-size') })
        await waitForNavigationMeasurement()
      }
      async function audit(name) {
        const title = { flow: 'Flow · Brand.Me', editorial: 'Editorial · Brand.Me', now: 'Now · Brand.Me', 'private-persona': 'Me · Brand.Me' }[name]
        // Keyboard navigation can render the client view before Next streams its metadata.
        await page.waitForFunction(expected => document.title === expected, title, { timeout: 10000 })
        for (const theme of ['light', 'dark']) {
          await page.emulateMedia({ colorScheme: theme })
          await page.waitForFunction(theme => document.documentElement.dataset.bmTheme === theme, theme)
          const accessibility = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze()
          assert.deepEqual(accessibility.violations.map(v => ({ id: v.id, targets: v.nodes.map(n => n.target) })), [], `${name}/${width}/${theme}`)
          assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `${name}/${width}: horizontal overflow`)
          await page.evaluate(() => { if (document.activeElement instanceof HTMLElement) document.activeElement.blur(); window.scrollTo(0, 0) })
          await page.evaluate(() => document.fonts.ready)
          await page.screenshot({ path: path.join(output, `${name}-${width}-${theme}.png`), fullPage: true, animations: 'disabled' })
          if (width === 1440 && name !== 'private-persona') {
            const bounds = await page.locator('.bm-social-streams').evaluate(element => {
              const main = element.querySelector('section').getBoundingClientRect()
              const brand = element.querySelector('aside').getBoundingClientRect()
              return { main: { top: main.top, right: main.right, width: main.width }, brand: { top: brand.top, left: brand.left } }
            })
            assert(Math.abs(bounds.main.top - bounds.brand.top) <= 1 && bounds.brand.left > bounds.main.right, `${name}: brand stream must sit alongside the main horizon`)
            assert(bounds.main.width >= 440, `${name}: main controls are too narrow`)
          }
          await inspectMobileScroll(name, theme)
        }
      }
      for (const horizon of ['flow', 'editorial']) {
        requests.length = 0
        await page.goto(`${base}/social/${horizon}`)
        const nav = page.getByRole('navigation', { name: 'Social horizons' })
        assert.equal(await nav.locator('[aria-current="page"]').getAttribute('href'), `/social/${horizon}`)
        assert.match(await page.locator('main').innerText(), /not available in this preview/i)
        assert.equal(await page.locator('main article, main img, main .bm-price').count(), 0)
        assert.equal(requests.length, 0, 'Unavailable horizons must not invent a feed API')
        await audit(horizon)
      }
      const horizonNavigation = page.getByRole('navigation', { name: 'Social horizons' })
      await horizonNavigation.getByRole('link', { name: 'Now', exact: true }).focus()
      await page.keyboard.press('Tab')
      assert(await horizonNavigation.getByRole('link', { name: 'Flow', exact: true }).evaluate(element => element === document.activeElement))
      await page.keyboard.press('Tab')
      assert(await horizonNavigation.getByRole('link', { name: 'Editorial', exact: true }).evaluate(element => element === document.activeElement))
      await page.keyboard.press('Shift+Tab')
      await page.keyboard.press('Enter')
      await page.waitForURL('**/social/flow')
      await page.locator('#horizon-flow').waitFor()
      assert.equal(await horizonNavigation.locator('[aria-current="page"]').getAttribute('href'), '/social/flow')
      await horizonNavigation.getByRole('link', { name: 'Flow', exact: true }).focus()
      await page.keyboard.press('Shift+Tab')
      await page.keyboard.press('Enter')
      await page.waitForURL('**/social/now')
      await page.locator('#horizon-now').waitFor()
      assert.equal(await horizonNavigation.locator('[aria-current="page"]').getAttribute('href'), '/social/now')
      await page.getByRole('link', { name: 'A friend asks about this look' }).waitFor()
      await page.getByRole('combobox', { name: 'Decisions to show' }).selectOption('mine')
      await page.getByRole('link', { name: 'My test request' }).waitFor()
      assert.equal(await page.locator('main .bm-price').count(), 0)
      assert.equal(requests.filter(r => r.path === '/relationships').length, 0, 'Now does not load friend management')
      assert.equal(await page.getByRole('link', { name: 'My test request' }).getAttribute('href'), `/circle/decisions/${decision}`)
      await audit('now')
      requests.length = 0
      await page.goto(`${base}/me`)
      await page.getByText('You’re exploring without a signed-in account. Sign in to see your saved style.', { exact: true }).waitFor()
      assert.deepEqual(requests.map(r => r.path), ['/me'], 'Guest cards must not request private domains')
      identity = 'unavailable'; requests.length = 0
      await page.reload()
      await page.getByRole('alert').filter({ hasText: 'not connected' }).waitFor()
      assert.equal(await page.getByText(/without a signed-in account/).count(), 0, 'Service failure is not proof of guest identity')
      assert.deepEqual(requests.map(r => r.path), ['/me'])
      identity = 'member'
      await page.reload()
      const card = page.getByRole('region', { name: 'Your private style card' })
      await card.getByText('Aster Test', { exact: true }).waitFor()
      await card.getByText('You chose: 72 · Locked', { exact: true }).waitFor()
      await card.getByText('Test contribution', { exact: true }).waitFor()
      await card.getByText('Aster saved jacket', { exact: true }).waitFor()
      assert.equal(await card.getByText('Palette', { exact: true }).count(), 0, 'Hidden axes must stay out of the card')
      assert.equal(await card.getByText('Unearned test badge', { exact: true }).count(), 0)
      assert.equal(await card.getByText('Wrong owner item', { exact: true }).count(), 0)
      assert.equal(await card.getByRole('link', { name: /follow|search people/i }).count(), 0)
      await audit('private-persona')
      revision = '2'
      await page.reload()
      await card.getByText('You chose: 24 · Locked', { exact: true }).waitFor()
      memberId = other
      await page.evaluate(() => window.dispatchEvent(new Event('brandme:account-change')))
      await card.getByText('Birch Test', { exact: true }).waitFor()
      await card.getByText('Birch saved coat', { exact: true }).waitFor()
      assert.equal(await page.getByText('Aster saved jacket', { exact: true }).count(), 0)
      assert.equal(await page.getByText('Aster Test', { exact: true }).count(), 0)
      identity = 'guest'; requests.length = 0
      await page.evaluate(() => window.dispatchEvent(new Event('brandme:account-change')))
      await page.getByText(/without a signed-in account/).waitFor()
      assert.equal(await card.count(), 0, 'Signing out clears the private card')
      assert.equal(requests.filter(r => r.method !== 'GET').length, 0, 'The preview is read-only')
      assert.deepEqual(errors, [], 'No browser runtime errors')
      results.push({ width, status: 'passed', keyboard_horizons: 'passed', mobile_scroll_text_scales: width <= 768 ? [100, 200] : [], parallel_stream: width === 1440 ? 'passed' : 'not_applicable', evidence: 'HTTP test doubles; not live-domain or human visual approval' })
      console.log(`PASS consumer rooms preview: ${width}px, both themes, identity gating, keyboard horizons and responsive scroll/layout checks`)
    } finally { await context.close() }
  }
} finally {
  await browser.close()
  await writeFile(path.join(output, 'results.json'), JSON.stringify({ status: results.length === 4 ? 'passed' : 'failed', visual_approval: 'not_run', results }, null, 2))
}

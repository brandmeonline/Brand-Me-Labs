/**
 * W01 behavioral/visual gate. Run against both apps in a browser-capable runtime.
 * Validation-only dependencies: playwright@1.58.2, @axe-core/playwright@4.10.2.
 * No account, provider, checkout or other domain writes are made by this suite.
 * Result stdout is evidence for the lane status file; never treat authored tests as passes.
 */
import { createRequire } from 'node:module'
import { mkdir } from 'node:fs/promises'
import path from 'node:path'

const require = createRequire(
  process.env.BRANDME_TEST_PACKAGE_JSON ||
    new URL('../../package.json', import.meta.url),
)
const { chromium } = require('playwright')
const AxeBuilder = require('@axe-core/playwright').default
const consumer = process.env.BRANDME_CONSUMER_URL || 'http://127.0.0.1:3000'
const consoleUrl = process.env.BRANDME_CONSOLE_URL || 'http://127.0.0.1:3002'
const output =
  process.env.BRANDME_EVIDENCE_DIR || path.resolve('shell-evidence')
const browser = await chromium.launch({ headless: true })
await mkdir(output, { recursive: true })
const failures = []
const checks = []
function assert(condition, message) {
  if (!condition) throw new Error(message)
}
async function check(name, fn) {
  try {
    await fn()
    checks.push(name)
    console.log(`PASS ${name}`)
  } catch (error) {
    failures.push({ name, message: error.message })
    console.error(`FAIL ${name}: ${error.message}`)
  }
}
async function noOverflow(page) {
  const bounds = await page.evaluate(() => ({
    document: document.documentElement.scrollWidth,
    viewport: innerWidth,
  }))
  assert(
    bounds.document <= bounds.viewport,
    `Document overflow: ${JSON.stringify(bounds)}`,
  )
}
async function audit(page) {
  const result = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21aa'])
    .analyze()
  assert(
    result.violations.length === 0,
    JSON.stringify(
      result.violations.map((v) => ({
        id: v.id,
        impact: v.impact,
        targets: v.nodes.map((n) => n.target),
      })),
    ),
  )
}
try {
  for (const [width, height] of [
    [320, 844],
    [390, 844],
    [768, 1024],
    [1440, 900],
  ]) {
    for (const [app, base, route] of [
      ['consumer', consumer, '/today'],
      ['console', consoleUrl, '/'],
    ]) {
      await check(
        `${app} ${width}x${height} light/dark and landmarks`,
        async () => {
          const context = await browser.newContext({
            viewport: { width, height },
            colorScheme: 'light',
          })
          try {
            const page = await context.newPage()
            const errors = []
            page.on('pageerror', (error) => errors.push(error.message))
            await page.goto(base + route, { waitUntil: 'networkidle' })
            await page.evaluate(() => document.fonts.ready)
            assert(
              (await page.locator('main').count()) === 1,
              'Expected one main landmark',
            )
            assert(
              (await page.locator('h1').count()) === 1,
              'Expected one page heading',
            )
            assert(
              (await page
                .locator('[data-nextjs-dialog], .vite-error-overlay')
                .count()) === 0,
              'Framework error overlay',
            )
            await noOverflow(page)
            await audit(page)
            await page.screenshot({
              path: path.join(output, `${app}-${width}x${height}-light.png`),
              fullPage: true,
            })
            await page.emulateMedia({ colorScheme: 'dark' })
            await page.waitForFunction(
              () =>
                getComputedStyle(document.documentElement)
                  .getPropertyValue('--bm-canvas')
                  .trim() === '#161817',
            )
            await noOverflow(page)
            await audit(page)
            await page.screenshot({
              path: path.join(output, `${app}-${width}x${height}-dark.png`),
              fullPage: true,
            })
            assert(errors.length === 0, errors.join('\n'))
          } finally {
            await context.close()
          }
        },
      )
    }
  }
  await check(
    'consumer keyboard skip, mobile dialog trap, snaps, Escape and focus return',
    async () => {
      const context = await browser.newContext({
        viewport: { width: 390, height: 844 },
      })
      try {
        const page = await context.newPage()
        await page.goto(consumer + '/today')
        await page.keyboard.press('Tab')
        assert(
          await page
            .locator('.bm-skip-link')
            .evaluate((e) => e === document.activeElement),
          'Skip link is not first',
        )
        await page.keyboard.press('Enter')
        assert(
          await page
            .locator('#main-content')
            .evaluate((e) => e === document.activeElement),
          'Skip link does not focus main',
        )
        const trigger = page.getByRole('button', {
          name: 'Open menu',
          exact: true,
        })
        await trigger.focus()
        await page.keyboard.press('Enter')
        const dialog = page.getByRole('dialog')
        await dialog.waitFor()
        for (const name of ['Compact', 'Medium', 'Full height']) {
          const button = dialog.getByRole('button', { name, exact: true })
          await button.focus()
          await page.keyboard.press('Space')
          assert(
            (await button.getAttribute('aria-pressed')) === 'true',
            `${name} not selected`,
          )
          await noOverflow(page)
        }
        for (let i = 0; i < 45; i++) {
          await page.keyboard.press('Tab')
          assert(
            await dialog.evaluate((e) => e.contains(document.activeElement)),
            'Focus escaped dialog',
          )
        }
        await page.keyboard.press('Escape')
        assert((await dialog.count()) === 0, 'Escape did not close dialog')
        assert(
          await trigger.evaluate((e) => e === document.activeElement),
          'Focus did not return to trigger',
        )
        await trigger.click()
        await dialog
          .getByRole('link', { name: 'Settings', exact: true })
          .click()
        await page.waitForURL('**/settings')
        assert(
          (await page.locator('h1').textContent()) === 'Comfort, by design.',
          'Menu route did not render',
        )
      } finally {
        await context.close()
      }
    },
  )
  await check(
    'display preferences survive reload; OS reduction wins; no camera or 3D dependencies',
    async () => {
      const context = await browser.newContext({
        viewport: { width: 390, height: 844 },
      })
      try {
        const page = await context.newPage()
        const requests = []
        page.on('request', (req) => requests.push(req.url()))
        await page.goto(consumer + '/settings')
        const main = page.locator('main')
        const dark = main.getByRole('radio', { name: 'Dark', exact: true })
        await dark.focus()
        await page.keyboard.press('Space')
        await main.getByRole('switch', { name: /Reduce motion/ }).check()
        await main.getByRole('switch', { name: /Prefer Simple View/ }).check()
        await page.reload()
        await main.getByRole('radio', { name: 'Dark', exact: true }).waitFor()
        assert(
          await main
            .getByRole('radio', { name: 'Dark', exact: true })
            .isChecked(),
          'Theme did not persist',
        )
        assert(
          await main
            .getByRole('switch', { name: /Prefer Simple View/ })
            .isChecked(),
          'Simple View preference did not persist',
        )
        assert(
          (await page
            .locator('.bm-route-content')
            .evaluate((e) => getComputedStyle(e).animationName)) === 'none',
          'In-app motion reduction missing',
        )
        await main.getByRole('switch', { name: /Reduce motion/ }).uncheck()
        await page.emulateMedia({ reducedMotion: 'reduce' })
        assert(
          (await page
            .locator('.bm-route-content')
            .evaluate((e) => getComputedStyle(e).animationName)) === 'none',
          'OS reduction was overridden',
        )
        await page.screenshot({
          path: path.join(output, 'consumer-reduced-motion.png'),
          fullPage: true,
        })
        assert(
          (await page.locator('canvas, video').count()) === 0,
          'Unexpected camera or canvas in shell',
        )
        assert(
          !requests.some((url) =>
            /mediapipe|three\.module|model-viewer|googleapis\.com\/css/.test(
              url,
            ),
          ),
          'Heavy/external visual dependency loaded',
        )
      } finally {
        await context.close()
      }
    },
  )
  await check(
    '200% reflow equivalent and 200% text remain usable',
    async () => {
      const context = await browser.newContext({
        viewport: { width: 720, height: 450 },
      })
      try {
        const page = await context.newPage()
        for (const route of ['/today', '/me', '/settings']) {
          await page.goto(consumer + route)
          await noOverflow(page)
          await page.evaluate(() => {
            document.documentElement.style.fontSize = '200%'
          })
          await noOverflow(page)
          await page.screenshot({
            path: path.join(
              output,
              `consumer-large-text-${route.slice(1)}.png`,
            ),
            fullPage: true,
          })
          await page.evaluate(() => {
            document.documentElement.style.fontSize = ''
          })
        }
        await page.setViewportSize({ width: 320, height: 844 })
        await page.goto(consumer + '/settings')
        await page.evaluate(() => {
          document.documentElement.style.fontSize = '200%'
        })
        await noOverflow(page)
      } finally {
        await context.close()
      }
    },
  )
  await check(
    'legacy redirects and unavailable stages are honest',
    async () => {
      const context = await browser.newContext()
      try {
        const page = await context.newPage()
        await page.goto(consumer + '/shop')
        assert(
          new URL(page.url()).pathname === '/discover',
          'Shop redirect missing',
        )
        assert(
          (await page.locator('main').innerText()).includes('not connected'),
          'Catalog displayed unsupported readiness',
        )
        await page.goto(consumer + '/stash')
        assert(
          new URL(page.url()).pathname === '/closet',
          'Stash redirect missing',
        )
        await page.goto(consumer + '/me/data')
        assert(
          (await page.locator('main').innerText()).includes('not connected'),
          'Privacy readiness overstated',
        )
      } finally {
        await context.close()
      }
    },
  )
  await check('console mobile menu keyboard and focus return', async () => {
    const context = await browser.newContext({
      viewport: { width: 320, height: 844 },
    })
    try {
      const page = await context.newPage()
      await page.goto(consoleUrl)
      const trigger = page.getByRole('button', { name: 'Open operations menu' })
      await trigger.focus()
      await page.keyboard.press('Enter')
      const dialog = page.getByRole('dialog')
      await dialog.waitFor()
      await noOverflow(page)
      for (let i = 0; i < 25; i++) {
        await page.keyboard.press('Tab')
        assert(
          await dialog.evaluate((e) => e.contains(document.activeElement)),
          'Console dialog focus escaped',
        )
      }
      await page.keyboard.press('Escape')
      assert(
        await trigger.evaluate((e) => e === document.activeElement),
        'Console focus not restored',
      )
    } finally {
      await context.close()
    }
  })
} finally {
  await browser.close()
}
console.log(
  JSON.stringify(
    {
      passed: checks.length,
      failed: failures.length,
      failures,
      screenshots: output,
    },
    null,
    2,
  ),
)
if (failures.length) process.exitCode = 1

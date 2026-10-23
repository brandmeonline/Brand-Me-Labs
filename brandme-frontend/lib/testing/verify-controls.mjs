/** Development-only browser gallery gate. Same validation dependencies as verify-shell.mjs.
 * Does not claim persistence or exercise domain APIs. Never run on a public production service.
 */
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { mkdir } from 'node:fs/promises'
import path from 'node:path'

const require = createRequire(
  process.env.BRANDME_TEST_PACKAGE_JSON ||
    new URL('../../package.json', import.meta.url),
)
const { chromium } = require('playwright')
const AxeBuilder = require('@axe-core/playwright').default
const base = process.env.BRANDME_CONSUMER_URL || 'http://127.0.0.1:3000'
const output =
  process.env.BRANDME_EVIDENCE_DIR || path.resolve('controls-evidence')
const browser = await chromium.launch({ headless: true })
await mkdir(output, { recursive: true })
try {
  for (const [width, height] of [
    [320, 844],
    [390, 844],
    [768, 1024],
    [1440, 900],
  ]) {
    const context = await browser.newContext({ viewport: { width, height } })
    try {
      const page = await context.newPage()
      const errors = []
      page.on('pageerror', (error) => errors.push(error.message))
      const response = await page.goto(`${base}/dev/components`, {
        waitUntil: 'networkidle',
      })
      assert.equal(
        response.status(),
        200,
        'Gallery requires a development server',
      )
      assert.equal(await page.locator('h1').textContent(), 'The small details.')
      assert.equal(await page.locator('main').count(), 1)
      for (const theme of ['light', 'dark']) {
        await page.emulateMedia({ colorScheme: theme })
        await page.waitForFunction(
          (theme) => document.documentElement.dataset.bmTheme === theme,
          theme,
        )
        await page.evaluate(() => document.fonts.ready)
        assert.ok(
          await page.evaluate(
            () => document.documentElement.scrollWidth <= innerWidth,
          ),
          'Horizontal overflow',
        )
        const report = await new AxeBuilder({ page })
          .withTags(['wcag2a', 'wcag2aa', 'wcag21aa'])
          .analyze()
        assert.deepEqual(
          report.violations.map(({ id, nodes }) => ({
            id,
            targets: nodes.map(({ target }) => target),
          })),
          [],
        )
        await page.screenshot({
          path: path.join(output, `controls-${width}-${theme}.png`),
          fullPage: true,
        })
      }
      const slider = page.getByRole('slider', {
        name: 'Expression',
        exact: true,
      })
      await slider.focus()
      assert.match(await slider.getAttribute('aria-valuetext'), /Not set/)
      await page.keyboard.press('ArrowRight')
      assert.equal(await slider.inputValue(), '55')
      await page.keyboard.press('Home')
      assert.equal(await slider.inputValue(), '0')
      await page
        .getByRole('spinbutton', { name: 'Expression value' })
        .fill('72')
      assert.equal(await slider.inputValue(), '72')
      await page
        .getByRole('spinbutton', { name: 'Expression value' })
        .fill('72.5')
      assert.equal(await slider.inputValue(), '72')
      await page.getByRole('button', { name: 'Clear expression' }).click()
      assert.match(await slider.getAttribute('aria-valuetext'), /Not set/)
      const firstTab = page.getByRole('tab', { name: 'Declared', exact: true })
      await firstTab.focus()
      await page.keyboard.press('End')
      assert.equal(
        await page
          .getByRole('tab', { name: 'Effective', exact: true })
          .getAttribute('aria-selected'),
        'true',
      )
      await page.keyboard.press('ArrowRight')
      assert.equal(await firstTab.getAttribute('aria-selected'), 'true')
      for (const type of ['dialog', 'drawer']) {
        const trigger = page.getByRole('button', {
          name: `Open example ${type}`,
        })
        await trigger.click()
        const dialog = page.getByRole('dialog')
        for (let i = 0; i < 16; i++) {
          await page.keyboard.press('Tab')
          assert.ok(
            await dialog.evaluate((element) =>
              element.contains(document.activeElement),
            ),
          )
        }
        await page.keyboard.press('Escape')
        assert.ok(
          await trigger.evaluate(
            (element) => element === document.activeElement,
          ),
        )
      }
      await page.getByRole('button', { name: 'Show example notice' }).click()
      assert.match(
        await page.locator('.bm-toast').textContent(),
        /Nothing was saved/,
      )
      await page.getByRole('button', { name: 'Dismiss notice' }).click()
      assert.ok(
        await page
          .getByRole('button', { name: 'Show example notice' })
          .evaluate((element) => element === document.activeElement),
      )
      await page.evaluate(() => {
        document.documentElement.style.fontSize = '200%'
      })
      assert.ok(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
        'Large text overflow',
      )
      assert.deepEqual(errors, [])
      console.log(
        `PASS gallery ${width}x${height}: light/dark, axe, keyboard, text reflow`,
      )
    } finally {
      await context.close()
    }
  }
  console.log(
    JSON.stringify({
      browser: browser.version(),
      viewports: 4,
      screenshots: output,
    }),
  )
} finally {
  await browser.close()
}

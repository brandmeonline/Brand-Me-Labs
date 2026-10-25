/** DecisionView integration with explicit HTTP doubles, a stub vibrator and simulated visibility.
 * This verifies browser wiring, not a live service, physical vibration or mobile-device behavior.
 * Run against a local build with useDecisionHeartbeat wired into DecisionView. No baselines change.
 */
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { mkdir, writeFile } from 'node:fs/promises'
import path from 'node:path'

const require = createRequire(process.env.BRANDME_TEST_PACKAGE_JSON || new URL('../../package.json', import.meta.url))
const { chromium } = require('playwright')
const base = process.env.BRANDME_CONSUMER_URL || 'http://127.0.0.1:3000'
const output = process.env.BRANDME_EVIDENCE_DIR
if (!output || !['localhost', '127.0.0.1'].includes(new URL(base).hostname)) throw new Error('Local UI test runner and evidence directory required')
await mkdir(output, { recursive: true })
const id = '12345678-1234-4234-8234-123456789012'
const preferenceKey = 'brandme:consumer:haptics:v1'
const checks = [], errors = [], requests = []
const browser = await chromium.launch({ headless: true })
let timedOut = false
const watchdog = setTimeout(() => { timedOut = true; void browser.close() }, 120_000)
const evidence = () => ({ evidence: 'HTTP doubles + stub vibrator + simulated visibility; no physical-device acceptance', viewport: '390x844', checks, errors, requests })

async function scenario({ supported = true, optedIn = false } = {}) {
  const context = await browser.newContext({ viewport: { width: 390, height: 844 }, reducedMotion: 'no-preference', timezoneId: 'UTC', serviceWorkers: 'block' })
  context.setDefaultTimeout(10_000)
  context.setDefaultNavigationTimeout(30_000)
  let members = ['friend-a'], requester = true, ownVote = false, readCount = 0, holdNext = false, release
  const payload = () => ({
    decision_id: id, creator_id: 'requester', prompt: 'Heartbeat integration fixture', state: 'open',
    subject_id: 'test-item', subject_type: 'wardrobe_item', server_time: '2026-10-23T00:00:00Z',
    closes_at: '2026-10-23T00:05:00Z', remaining_seconds: 300, response_count: members.length,
    responses_hidden_until_you_answer: !requester && !ownVote,
    my_response: ownVote ? { choice: 'yes' } : null,
    responses: !requester && !ownVote ? [] : members.map(respondent_id => ({ respondent_id, choice: 'yes', note: `Fixture reply ${respondent_id}` })),
    ...(requester ? { audience: 'abcdefghi'.split('').map(letter => `friend-${letter}`) } : {}),
  })
  await context.addInitScript(({ supported, optedIn, preferenceKey }) => {
    if (localStorage.getItem(preferenceKey) === null) localStorage.setItem(preferenceKey, JSON.stringify({ friendResponses: optedIn }))
    window.__heartbeatFixture = { calls: [], visibility: 'visible' }
    Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => window.__heartbeatFixture.visibility })
    Object.defineProperty(navigator, 'vibrate', { configurable: true, value: supported
      ? pattern => { window.__heartbeatFixture.calls.push(Array.isArray(pattern) ? [...pattern] : pattern); return true }
      : undefined })
  }, { supported, optedIn, preferenceKey })
  await context.route('**/api/v1/**', async route => {
    const req = route.request(), endpoint = new URL(req.url()).pathname.replace('/api/v1', '')
    requests.push({ method: req.method(), path: endpoint, supported })
    const reply = data => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(data) })
    if (endpoint === `/decisions/${id}` && req.method() === 'GET') {
      readCount++
      const data = payload()
      if (holdNext) { holdNext = false; await new Promise(resolve => { release = resolve }) }
      return reply(data)
    }
    if (endpoint === '/session' && req.method() === 'GET') return reply({ csrf_token: 'explicit-http-test-double' })
    if (endpoint === `/decisions/${id}/responses` && req.method() === 'POST') {
      assert.equal(req.postDataJSON().choice, 'yes')
      ownVote = true; members.push('recipient')
      return reply({ recorded: true })
    }
    errors.push(`Unexpected HTTP double: ${req.method()} ${endpoint}`)
    return route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ code: 'unavailable', title: 'No test double for this service' }) })
  })
  const page = await context.newPage()
  page.on('pageerror', error => errors.push(error.message))
  // The actual 30-second DecisionView polling interval drives resource reloads.
  // Playwright clock: https://playwright.dev/docs/clock
  await page.clock.install({ time: new Date('2026-10-23T00:00:00Z') })
  const pulses = () => page.evaluate(() => window.__heartbeatFixture.calls.filter(Array.isArray))
  const settle = () => new Promise(resolve => setTimeout(resolve, 100))
  async function pulseCount(expected, name) {
    await settle()
    assert.equal((await pulses()).length, expected, name)
    checks.push(name)
  }
  async function waitForRead(previous) {
    for (let attempt = 0; readCount <= previous && attempt < 100; attempt++) await settle()
    assert.ok(readCount > previous, 'The real DecisionView must reload its HTTP resource')
  }
  async function poll(member) {
    if (member) members.push(member)
    const previous = readCount
    await page.clock.fastForward(30_001)
    await waitForRead(previous)
    if (member) await page.getByText(`yes — Fixture reply ${member}`, { exact: true }).waitFor()
    await settle()
  }
  async function visible(value) {
    await page.evaluate(value => {
      window.__heartbeatFixture.visibility = value ? 'visible' : 'hidden'
      document.dispatchEvent(new Event('visibilitychange'))
    }, value)
  }
  async function settings(label, enabled) {
    await page.getByRole('button', { name: 'Open menu', exact: true }).click()
    const control = page.getByRole('dialog').getByRole('switch', { name: label, exact: true })
    await control.setChecked(enabled)
    assert.equal(await control.isChecked(), enabled)
    await page.keyboard.press('Escape')
    await page.getByRole('dialog').waitFor({ state: 'hidden' })
  }
  try {
    await page.goto(`${base}/circle/decisions/${id}`)
    await page.getByRole('heading', { name: 'Heartbeat integration fixture' }).waitFor()
    await pulseCount(0, `${supported ? 'supported' : 'unsupported'} initial render is silent`)
    if (!supported) {
      await settings('Friend response heartbeat', true)
      await poll('friend-b')
      await pulseCount(0, 'unsupported vibration leaves response rendering intact')
      return
    }
    await poll('friend-b')
    await pulseCount(0, 'opt-out consumes new HTTP responses silently')
    await settings('Friend response heartbeat', true)
    assert.deepEqual(await page.evaluate(key => JSON.parse(localStorage.getItem(key)), preferenceKey), { friendResponses: true })
    await pulseCount(0, 'accessible opt-in persists without replaying existing replies')
    await page.reload()
    await page.getByText('yes — Fixture reply friend-b', { exact: true }).waitFor()
    // A real trusted interaction establishes sticky activation after the reload.
    await settings('Friend response heartbeat', true)
    await pulseCount(0, 'full document reload starts from a silent baseline')
    await poll('friend-c')
    await pulseCount(1, 'new requester response after actual HTTP polling causes one heartbeat')
    assert.deepEqual(await pulses(), [[25, 50, 25]])
    await poll()
    await pulseCount(1, 'duplicate HTTP snapshots do not replay the heartbeat')
    await page.emulateMedia({ reducedMotion: 'reduce' })
    await page.waitForFunction(() => document.documentElement.dataset.motion === 'reduced')
    await poll('friend-d')
    await pulseCount(1, 'OS reduced motion suppresses new responses')
    await page.emulateMedia({ reducedMotion: 'no-preference' })
    await settings('Reduce motion', true)
    await poll('friend-e')
    await settings('Reduce motion', false)
    await pulseCount(1, 'app reduced motion suppresses responses without catch-up')

    // Hold a real fetch, hide, then deliver it: polling itself is suppressed while hidden.
    members.push('friend-f'); holdNext = true
    const beforeHold = readCount
    await page.clock.fastForward(30_001); await waitForRead(beforeHold)
    assert.equal(typeof release, 'function')
    await visible(false); release(); release = undefined
    await page.getByText('yes — Fixture reply friend-f', { exact: true }).waitFor()
    await pulseCount(1, 'an in-flight response delivered to a simulated hidden tab is silent')
    const hiddenReads = readCount
    await page.clock.fastForward(30_001); await settle()
    assert.equal(readCount, hiddenReads, 'hidden DecisionView must not poll')
    members.push('friend-g'); await visible(true); await waitForRead(hiddenReads)
    await page.getByText('yes — Fixture reply friend-g', { exact: true }).waitFor()
    await pulseCount(1, 'visibility refresh establishes a silent baseline')
    await poll('friend-h')
    await pulseCount(2, 'new responses resume after the visibility baseline')
    members.push('friend-i')
    const beforeAccount = readCount
    await page.evaluate(() => window.dispatchEvent(new Event('brandme:account-change')))
    await waitForRead(beforeAccount)
    await page.getByText('yes — Fixture reply friend-i', { exact: true }).waitFor()
    await pulseCount(2, 'account-change reload establishes a silent baseline')

    requester = false; members = ['friend-a']; await page.reload()
    await page.getByText('Other responses stay hidden until you answer.', { exact: true }).waitFor()
    await page.getByRole('button', { name: 'Yes', exact: true }).click()
    await page.getByText('Your response: yes', { exact: true }).waitFor()
    await pulseCount(0, 'recipient own-vote command and reload remain silent')
    await poll('friend-b')
    await pulseCount(0, 'recipient-visible friend replies remain silent')
  } finally {
    release?.()
    await context.close()
  }
}

try {
  await scenario()
  await scenario({ supported: false, optedIn: true })
  assert.deepEqual(errors, [])
  await writeFile(path.join(output, 'decision-haptics.json'), JSON.stringify({ ...evidence(), result: 'pass' }, null, 2))
  console.log(`PASS DecisionView: ${checks.length} browser checks at 390x844; explicit HTTP doubles, stub vibrator and simulated visibility only`)
} catch (error) {
  await writeFile(path.join(output, 'decision-haptics.json'), JSON.stringify({ ...evidence(), result: 'fail', error: timedOut ? '120-second runner deadline exceeded' : error.message }, null, 2))
  throw error
} finally {
  clearTimeout(watchdog)
  await browser.close()
}

/** Start already-built apps on ephemeral loopback ports, inspect HTTP, then stop them.
 * Not browser, hydration, accessibility, database, or provider evidence.
 * Requires each app's dependencies and successful next build output.
 */
import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { once } from 'node:events'
import { createRequire } from 'node:module'
import { createServer } from 'node:net'
import { fileURLToPath } from 'node:url'

const root = new URL('../../../', import.meta.url)
const servers = []
const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms))
async function start(app) {
  const reservation = createServer()
  reservation.listen(0, '127.0.0.1')
  await once(reservation, 'listening')
  const port = reservation.address().port
  await new Promise((resolve, reject) =>
    reservation.close((error) => (error ? reject(error) : resolve())),
  )
  const directory = new URL(`${app}/`, root)
  const require = createRequire(new URL('package.json', directory))
  const processRef = spawn(
    process.execPath,
    [
      require.resolve('next/dist/bin/next'),
      'start',
      '-H',
      '127.0.0.1',
      '-p',
      String(port),
    ],
    {
      cwd: fileURLToPath(directory),
      env: {
        ...process.env,
        NODE_ENV: 'production',
        NEXT_TELEMETRY_DISABLED: '1',
        BRANDME_MODE: 'sandbox',
      },
      stdio: ['ignore', 'pipe', 'pipe'],
    },
  )
  const server = { processRef, base: `http://127.0.0.1:${port}`, errors: '' }
  servers.push(server)
  processRef.stdout.on('data', () => {})
  processRef.stderr.on('data', (data) => {
    server.errors = (server.errors + data).slice(-4000)
  })
  let startupError
  processRef.on('error', (error) => {
    startupError = error
  })
  const deadline = Date.now() + 30000
  while (Date.now() < deadline) {
    if (startupError) throw startupError
    if (processRef.exitCode !== null)
      throw new Error(`${app} exited: ${server.errors}`)
    try {
      await fetch(server.base, { signal: AbortSignal.timeout(500) })
      return server
    } catch {}
    await delay(100)
  }
  throw new Error(`${app} did not start: ${server.errors}`)
}
async function html(server, route, expected = 200) {
  const response = await fetch(server.base + route, {
    redirect: 'manual',
    signal: AbortSignal.timeout(5000),
  })
  assert.equal(response.status, expected, `${route}: status`)
  return response.text()
}
try {
  const consumer = await start('brandme-frontend')
  const consoleApp = await start('brandme-console')
  const routes = [
    '/',
    '/today',
    '/me',
    '/settings',
    '/start',
    '/me/style',
    '/me/data',
    '/me/connections',
    '/circle',
    '/discover',
    '/assistant',
    '/rewards',
    '/orders',
    '/inbox',
  ]
  for (const route of routes) {
    const body = await html(consumer, route)
    assert.equal(
      (body.match(/<main(?:\s|>)/g) || []).length,
      1,
      `${route}: main`,
    )
    assert.equal((body.match(/<h1(?:\s|>)/g) || []).length, 1, `${route}: h1`)
    assert.ok(
      body.includes('#F6F3ED') && body.includes('#161817'),
      `${route}: theme tokens`,
    )
  }
  const hidden = await html(consumer, '/dev/components', 404)
  assert.ok(
    !hidden.includes('The small details.'),
    'Gallery rendered in production',
  )
  for (const [from, to] of [
    ['/shop', '/discover'],
    ['/stash', '/closet'],
  ]) {
    for (const method of ['GET', 'HEAD']) {
      const response = await fetch(consumer.base + from, {
        method,
        redirect: 'manual',
      })
      assert.equal(response.status, 307)
      assert.equal(
        new URL(response.headers.get('location'), consumer.base).pathname,
        to,
      )
    }
  }
  for (const server of [consumer, consoleApp]) {
    const body = await html(server, '/')
    const fonts = [
      ...new Set(
        [...body.matchAll(/href="([^"]+\.woff2[^"<>]*)"/g)].map(
          (match) => match[1],
        ),
      ),
    ]
    assert.equal(fonts.length, 5, 'Five self-hosted fonts')
    for (const font of fonts) {
      const response = await fetch(new URL(font, server.base))
      assert.equal(response.status, 200)
      assert.ok((await response.arrayBuffer()).byteLength > 1000)
    }
  }
  const operations = await html(consoleApp, '/')
  assert.ok(operations.includes('sandbox environment'), 'Console runtime mode')
  assert.equal((operations.match(/<main(?:\s|>)/g) || []).length, 1)
  assert.equal((operations.match(/<h1(?:\s|>)/g) || []).length, 1)
  assert.ok((await html(consumer, '/me/data')).includes('not connected'))
  console.log(
    'PASS production HTTP: 14 consumer routes + console root; gallery 404; GET/HEAD redirects; 10 font deliveries; runtime mode; honest privacy state',
  )
} finally {
  await Promise.all(
    servers.map(async ({ processRef }) => {
      if (processRef.exitCode !== null) return
      const closed = once(processRef, 'close')
      processRef.kill('SIGTERM')
      await Promise.race([closed, delay(2000)])
      if (processRef.exitCode === null && processRef.signalCode === null) {
        processRef.kill('SIGKILL')
        await closed
      }
    }),
  )
}

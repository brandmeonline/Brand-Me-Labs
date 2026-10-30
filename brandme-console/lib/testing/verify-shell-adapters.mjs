/** Adapter parity only; production build verifies real Next font loading.
 * BRANDME_TEST_PACKAGE_JSON can select an existing full install without changing the filtered install.
 */
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { test } from 'node:test'

const require = createRequire(process.env.BRANDME_TEST_PACKAGE_JSON || new URL('../../package.json', import.meta.url))
const ts = require('typescript')
const { tokens } = require('@brandme/design-system')
const consoleRoot = new URL('../', import.meta.url)
const consumerRoot = new URL('../../brandme-frontend/lib/', consoleRoot)

function adapter(url, dependency = require) {
  const compiled = ts.transpileModule(readFileSync(url, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, esModuleInterop: true },
    fileName: fileURLToPath(url),
  }).outputText
  const exports = {}
  new Function('require', 'exports', compiled)(dependency, exports)
  return exports
}

test('console CSS adapter remains byte-for-byte equivalent and uses foundation token values', () => {
  const local = adapter(new URL('design-tokens.ts', consoleRoot))
  const consumer = adapter(new URL('design-tokens.ts', consumerRoot))
  assert.equal(local.tokens, tokens)
  assert.equal(local.designTokenCss(), consumer.designTokenCss())
})

test('console font declarations retain every shared asset and font option', () => {
  const declaration = url => adapter(url, name => {
    assert.equal(name, 'next/font/local')
    return options => ({ ...options, src: typeof options.src === 'string'
      ? path.resolve(path.dirname(fileURLToPath(url)), options.src)
      : options.src.map(source => ({ ...source, path: path.resolve(path.dirname(fileURLToPath(url)), source.path) })) })
  })
  assert.deepEqual(declaration(new URL('fonts.ts', consoleRoot)), declaration(new URL('fonts.ts', consumerRoot)))
})

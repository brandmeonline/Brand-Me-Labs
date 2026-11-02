/** Stub-vibrator hook checks only; this is not physical-device haptic evidence. */
import assert from 'node:assert/strict'
import { test } from 'node:test'

export function registerHapticsTests({ source, React, render, cleanup, act }) {
  const { useDecisionHeartbeat } = source('../../features/social/use-decision-heartbeat.ts')
  const { useFriendResponseHaptics } = source('../client/haptic-preferences.ts')
  const { ExperiencePreferencesProvider, useExperiencePreferences } = source('../client/experience-preferences.tsx')
  const key = 'brandme:consumer:haptics:v1'
  const h = React.createElement
  const decision = (respondents = [], overrides = {}) => ({
    decision_id: 'request-a', creator_id: 'requester', audience: ['friend-a', 'friend-b'],
    responses_hidden_until_you_answer: false,
    responses: respondents.map(respondent_id => ({ respondent_id, choice: 'yes', note: null })),
    ...overrides,
  })

  function fixture({ enabled = true, reducedMotion = false, vibrate = true, activation = true } = {}) {
    const original = {
      media: globalThis.matchMedia,
      storage: Object.getOwnPropertyDescriptor(globalThis, 'localStorage'),
      channel: globalThis.BroadcastChannel,
      visibility: Object.getOwnPropertyDescriptor(document, 'visibilityState'),
      vibrate: Object.getOwnPropertyDescriptor(navigator, 'vibrate'),
      activation: Object.getOwnPropertyDescriptor(navigator, 'userActivation'),
    }
    const calls = [], channels = [], motionListeners = new Set()
    let visibility = 'visible', reduced = reducedMotion, hapticPreference, displayPreference
    window.localStorage.clear()
    window.localStorage.setItem(key, JSON.stringify({ friendResponses: enabled }))
    Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: window.localStorage })
    Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => visibility })
    Object.defineProperty(navigator, 'userActivation', { configurable: true, value: { hasBeenActive: activation } })
    Object.defineProperty(navigator, 'vibrate', { configurable: true, writable: true,
      value: vibrate ? pattern => { calls.push(Array.isArray(pattern) ? [...pattern] : pattern); return true } : undefined })
    globalThis.matchMedia = query => ({
      get matches() { return query.includes('reduced-motion') && reduced },
      addEventListener: (_, listener) => { if (query.includes('reduced-motion')) motionListeners.add(listener) },
      removeEventListener: (_, listener) => motionListeners.delete(listener),
    })
    globalThis.BroadcastChannel = class {
      constructor(name) { this.name = name; channels.push(this) }
      addEventListener(_, listener) { this.listener = listener }
      close() { this.closed = true }
    }
    function Observer({ id, snapshot }) {
      hapticPreference = useFriendResponseHaptics()
      displayPreference = useExperiencePreferences()
      useDecisionHeartbeat(id, snapshot)
      return null
    }
    const element = (snapshot, id = 'request-a') => h(ExperiencePreferencesProvider, null, h(Observer, { id, snapshot }))
    let view
    const restore = (object, name, descriptor) => descriptor
      ? Object.defineProperty(object, name, descriptor) : delete object[name]
    return {
      calls, channels, pulses: () => calls.filter(Array.isArray),
      show(snapshot, id) { if (view) view.rerender(element(snapshot, id)); else view = render(element(snapshot, id)) },
      enabled(value) { act(() => hapticPreference.setEnabled(value)) },
      appReduced(value) { act(() => displayPreference.update({ motion: value ? 'reduce' : 'system' })) },
      osReduced(value) { reduced = value; act(() => motionListeners.forEach(listener => listener())) },
      visible(value) { visibility = value ? 'visible' : 'hidden'; act(() => document.dispatchEvent(new Event('visibilitychange'))) },
      account() { act(() => window.dispatchEvent(new Event('brandme:account-change'))) },
      remoteAccount() { act(() => channels.filter(channel => !channel.closed).forEach(channel => channel.listener())) },
      unmount() { view?.unmount(); view = null },
      finish() {
        cleanup()
        globalThis.matchMedia = original.media
        globalThis.BroadcastChannel = original.channel
        restore(globalThis, 'localStorage', original.storage)
        restore(document, 'visibilityState', original.visibility)
        restore(navigator, 'vibrate', original.vibrate)
        restore(navigator, 'userActivation', original.activation)
      },
    }
  }

  test('heartbeat opt-in uses its consumer key, survives a remount and defaults corrupt data to off', () => {
    const f = fixture({ enabled: false })
    try {
      const display = JSON.stringify({ theme: 'dark', motion: 'system', simpleView: false, highContrast: false })
      localStorage.setItem('brandme:experience:v1', display)
      f.show(decision()); f.enabled(true)
      assert.deepEqual(JSON.parse(localStorage.getItem(key)), { friendResponses: true })
      assert.equal(localStorage.getItem('brandme:experience:v1'), display)
      f.unmount(); f.show(decision()); f.show(decision(['friend-a']))
      assert.equal(f.pulses().length, 1)
      localStorage.setItem(key, '{invalid')
      act(() => window.dispatchEvent(new window.StorageEvent('storage', { key })))
      f.show(decision(['friend-a', 'friend-b']))
      assert.equal(f.pulses().length, 1)
    } finally { f.finish() }
  })

  test('heartbeat ignores initial and duplicate reload snapshots and uses response IDs rather than counts', () => {
    const f = fixture()
    try {
      f.show(decision(['friend-a'])); f.show(null); f.show(decision(['friend-a'], { response_count: 99 }))
      assert.deepEqual(f.pulses(), [])
      f.show(decision(['friend-a', 'friend-b']))
      assert.deepEqual(f.pulses(), [[25, 50, 25]])
      f.show(decision(['friend-a', 'friend-b']))
      assert.equal(f.pulses().length, 1)
      f.unmount(); f.show(decision(['friend-a', 'friend-b', 'friend-c']))
      assert.equal(f.pulses().length, 1)
    } finally { f.finish() }
  })

  test('heartbeat is requester-only and never reacts to the requester own response or hidden replies', () => {
    const f = fixture()
    try {
      f.show(decision()); f.show(decision(['requester']))
      assert.deepEqual(f.pulses(), [])
      f.show(decision(['friend-a'], { audience: undefined })); f.show(decision(['friend-a', 'friend-b'], { audience: undefined }))
      f.show(decision(['friend-a'], { responses_hidden_until_you_answer: true }))
      f.show(decision(['friend-a', 'friend-b']))
      assert.deepEqual(f.pulses(), [])
      f.show(decision(['friend-a', 'friend-b', 'friend-c']))
      assert.equal(f.pulses().length, 1)
    } finally { f.finish() }
  })

  test('disabled and reduced-motion responses are consumed silently without catch-up pulses', () => {
    const f = fixture({ enabled: false })
    try {
      f.show(decision()); f.show(decision(['friend-a'])); f.enabled(true)
      assert.deepEqual(f.pulses(), [])
      f.osReduced(true); f.show(decision(['friend-a', 'friend-b'])); f.osReduced(false)
      f.appReduced(true); f.show(decision(['friend-a', 'friend-b', 'friend-c'])); f.appReduced(false)
      assert.deepEqual(f.pulses(), [])
      f.show(decision(['friend-a', 'friend-b', 'friend-c', 'friend-d']))
      assert.equal(f.pulses().length, 1)
      f.enabled(false)
      assert.equal(f.calls.at(-1), 0)
    } finally { f.finish() }
  })

  test('hidden-tab responses and the first resumed snapshot remain silent', () => {
    const f = fixture()
    try {
      f.show(decision()); f.visible(false); f.show(decision(['friend-a']))
      f.visible(true); f.show(decision(['friend-a', 'friend-b']))
      assert.deepEqual(f.pulses(), [])
      f.show(decision(['friend-a', 'friend-b', 'friend-c']))
      assert.equal(f.pulses().length, 1)
      f.visible(false)
      assert.equal(f.calls.at(-1), 0)
    } finally { f.finish() }
  })

  test('account events and decision switches reset the baseline and stop an active heartbeat', () => {
    const f = fixture()
    try {
      f.show(decision()); f.show(decision(['friend-a'])); f.account()
      assert.equal(f.calls.at(-1), 0)
      f.show(decision(['friend-a', 'friend-b']))
      f.remoteAccount(); f.show(decision(['friend-a', 'friend-b', 'friend-c']))
      f.show(decision(['friend-a', 'friend-b', 'friend-c']), 'request-b')
      f.show(decision(['friend-d'], { decision_id: 'request-b' }), 'request-b')
      assert.equal(f.pulses().length, 1)
      f.show(decision(['friend-d', 'friend-e'], { decision_id: 'request-b' }), 'request-b')
      assert.equal(f.pulses().length, 2)
      f.unmount()
      assert.equal(f.calls.at(-1), 0)
      assert.ok(f.channels.every(channel => channel.closed))
    } finally { f.finish() }
  })

  test('unsupported, false-returning and throwing vibration implementations do not interrupt the decision', () => {
    const f = fixture({ vibrate: false })
    try {
      f.show(decision()); f.show(decision(['friend-a']))
      navigator.vibrate = () => false
      f.show(decision(['friend-a', 'friend-b']))
      let attempts = 0
      navigator.vibrate = () => { attempts++; throw new Error('Unavailable') }
      f.show(decision(['friend-a', 'friend-b', 'friend-c']))
      f.show(decision(['friend-a', 'friend-b', 'friend-c']))
      assert.equal(attempts, 1)
    } finally { f.finish() }
  })

  test('missing sticky activation stays silent and is not replayed when activation arrives', () => {
    const f = fixture({ activation: false })
    try {
      f.show(decision()); f.show(decision(['friend-a']))
      navigator.userActivation.hasBeenActive = true
      f.show(decision(['friend-a']))
      assert.deepEqual(f.pulses(), [])
      f.show(decision(['friend-a', 'friend-b']))
      assert.equal(f.pulses().length, 1)
    } finally { f.finish() }
  })
}

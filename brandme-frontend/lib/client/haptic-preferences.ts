'use client'
import { useSyncExternalStore } from 'react'

// Consumer-only presentation preference; the console's experience:v1 stays unchanged.
const storageKey = 'brandme:consumer:haptics:v1'
type Preference = { enabled: boolean; ready: boolean; storageAvailable: boolean }
const initial: Preference = { enabled: false, ready: false, storageAvailable: true }
let snapshot = initial
const listeners = new Set<() => void>()

function publish(next: Preference) {
  if (next.enabled === snapshot.enabled && next.ready === snapshot.ready &&
      next.storageAvailable === snapshot.storageAvailable) return
  snapshot = next
  listeners.forEach(listener => listener())
}
function read() {
  let raw: string | null
  try {
    raw = window.localStorage.getItem(storageKey)
  } catch {
    publish({ ...snapshot, ready: true, storageAvailable: false })
    return
  }
  let enabled = false
  try { enabled = JSON.parse(raw || '{}')?.friendResponses === true } catch { /* Corrupt opt-in is off. */ }
  publish({ enabled, ready: true, storageAvailable: true })
}
function storageChanged(event: StorageEvent) {
  if (event.key === storageKey || event.key === null) read()
}
function subscribe(listener: () => void) {
  listeners.add(listener)
  if (listeners.size === 1) window.addEventListener('storage', storageChanged)
  read()
  return () => {
    listeners.delete(listener)
    if (!listeners.size) window.removeEventListener('storage', storageChanged)
  }
}
function setEnabled(enabled: boolean) {
  let storageAvailable = true
  try { window.localStorage.setItem(storageKey, JSON.stringify({ friendResponses: enabled })) }
  catch { storageAvailable = false }
  publish({ enabled, ready: true, storageAvailable })
}

export function useFriendResponseHaptics() {
  const preference = useSyncExternalStore(subscribe, () => snapshot, () => initial)
  return { ...preference, setEnabled }
}

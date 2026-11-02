'use client'
import { useCallback, useEffect, useRef } from 'react'
import { useExperiencePreferences } from '../../lib/client/experience-preferences'
import { useFriendResponseHaptics } from '../../lib/client/haptic-preferences'

type DecisionResponseSnapshot = {
  decision_id: string
  creator_id: string
  audience?: string[]
  responses_hidden_until_you_answer: boolean
  responses: { respondent_id: string }[]
}
type Observation = { id: string; creator: string; respondents: Set<string> }
const heartbeat = [25, 50, 25]

/** Optional feedback for actual new requester-visible responses, never a notification feed.
 * Vibration API: https://www.w3.org/TR/vibration/#vibration-interface
 * A true API return is not evidence that a device physically vibrated.
 */
export function useDecisionHeartbeat(id: string, decision: DecisionResponseSnapshot | null) {
  const { enabled, ready } = useFriendResponseHaptics()
  const { reducedMotion } = useExperiencePreferences()
  const observed = useRef<Observation | null>(null)
  const latest = useRef<DecisionResponseSnapshot | null>(null)
  const blockedSnapshot = useRef<DecisionResponseSnapshot | null>(null)
  const route = useRef(id)
  const active = useRef<ReturnType<typeof setTimeout> | null>(null)
  const cancel = useCallback(() => {
    if (active.current === null) return
    clearTimeout(active.current)
    active.current = null
    try { navigator.vibrate?.(0) } catch { /* Optional enhancement. */ }
  }, [])

  useEffect(() => {
    const reset = () => {
      observed.current = null
      blockedSnapshot.current = latest.current
      cancel()
    }
    // Reset on both hide and return: a hidden-tab backlog must not produce a pulse.
    document.addEventListener('visibilitychange', reset)
    window.addEventListener('brandme:account-change', reset)
    let channel: BroadcastChannel | undefined
    try {
      if (typeof BroadcastChannel !== 'undefined') {
        channel = new BroadcastChannel('brandme:account')
        channel.addEventListener('message', reset)
      }
    } catch { /* The same-tab account event still works when channels are unavailable. */ }
    return () => {
      document.removeEventListener('visibilitychange', reset)
      window.removeEventListener('brandme:account-change', reset)
      channel?.close()
      observed.current = null
      cancel()
    }
  }, [cancel])

  useEffect(() => {
    latest.current = decision
    if (route.current !== id) {
      route.current = id
      observed.current = null
      blockedSnapshot.current = null
      cancel()
    }
    if (!enabled || !ready || reducedMotion) cancel()
    // A routine resource revalidation temporarily clears data. Preserve its known
    // response IDs; a fresh mount/account/route still starts from a silent baseline.
    if (!decision || decision === blockedSnapshot.current) return
    blockedSnapshot.current = null
    if (decision.decision_id !== id || !Array.isArray(decision.audience) ||
        decision.responses_hidden_until_you_answer || !Array.isArray(decision.responses)) {
      observed.current = null
      return
    }
    const respondents = new Set(decision.responses
      .map(response => response.respondent_id)
      .filter(member => typeof member === 'string' && member.length > 0 && member !== decision.creator_id))
    const previous = observed.current
    const sameRequest = previous?.id === id && previous.creator === decision.creator_id
    const added = sameRequest && [...respondents].some(member => !previous.respondents.has(member))
    observed.current = {
      id, creator: decision.creator_id,
      respondents: new Set([...(sameRequest ? previous.respondents : []), ...respondents]),
    }
    if (!added || !enabled || !ready || reducedMotion || document.visibilityState !== 'visible' ||
        active.current !== null) return
    try {
      if (typeof navigator.vibrate !== 'function' || navigator.userActivation?.hasBeenActive === false) return
      if (navigator.vibrate(heartbeat)) {
        active.current = setTimeout(() => { active.current = null }, 100)
      }
    } catch { /* Unsupported or denied vibration never changes the decision flow. */ }
  }, [id, decision, enabled, ready, reducedMotion, cancel])
}

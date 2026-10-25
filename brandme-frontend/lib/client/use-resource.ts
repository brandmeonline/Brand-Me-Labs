'use client'
import { useCallback, useEffect, useRef, useState } from 'react'
import { invalidateAccountRequests, read, type Resource } from './gateway'

/** No shared account cache. Abort obsolete reads; clear records on account changes. */
export function useResource<T>(path: string | null) {
  const [state, setState] = useState<Resource<T>>({ data: null, error: null, loading: true })
  const [revision, setRevision] = useState(0)
  const abort = useRef<AbortController | null>(null)
  const reload = useCallback(() => setRevision(v => v + 1), [])
  useEffect(() => {
    abort.current?.abort()
    const controller = new AbortController(); abort.current = controller
    setState({ data: null, error: null, loading: Boolean(path) })
    if (path) read<T>(path, controller.signal).then(data => {
      if (!controller.signal.aborted) setState({ data, error: null, loading: false })
    }).catch(error => {
      if (!controller.signal.aborted) setState({ data: null, error, loading: false })
    })
    return () => controller.abort()
  }, [path, revision])
  useEffect(() => {
    const clear = () => { invalidateAccountRequests(); abort.current?.abort(); setState({ data: null, error: null, loading: true }); reload() }
    const channel = typeof BroadcastChannel !== 'undefined' ? new BroadcastChannel('brandme:account') : null
    channel?.addEventListener('message', clear)
    window.addEventListener('brandme:account-change', clear)
    return () => { channel?.close(); window.removeEventListener('brandme:account-change', clear) }
  }, [reload])
  return { ...state, reload }
}

export function accountChanged() {
  invalidateAccountRequests()
  window.dispatchEvent(new Event('brandme:account-change'))
  if (typeof BroadcastChannel !== 'undefined') { const channel = new BroadcastChannel('brandme:account'); channel.postMessage('changed'); channel.close() }
}

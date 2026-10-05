/**
 * Realtime client.
 *
 * Wraps `EventSource` and the WebSocket behind one hook so a screen asks for a topic
 * and gets typed events, with reconnection handled here rather than in every consumer.
 *
 * SSE is the default because the browser reconnects it on its own and it passes
 * through the same bearer-token auth as any other request. The access token is
 * supplied as a query parameter, since `EventSource` cannot set headers.
 */

import { useEffect, useRef, useState } from 'react'

import { tokenStore } from '@/lib/api'

const API_BASE = (import.meta.env.VITE_API_BASE_URL as string) ?? '/api/v1'

/** Server-Sent Events topics, matching `app/api/routers/stream.py`. */
export type StreamTopic = 'run' | 'job' | 'kpi' | 'change' | 'quality' | 'notification'

export type StreamEvent = {
  topic: string
  at: string
  kind?: string
  [key: string]: unknown
}

export type ConnectionState = 'connecting' | 'open' | 'closed' | 'error'

function streamUrl(topics: StreamTopic[]): string {
  const params = new URLSearchParams({ topics: topics.join(',') })
  const token = tokenStore.get()
  if (token) params.set('token', token)
  return `${API_BASE}/stream/everything?${params.toString()}`
}

/**
 * Subscribe to one or more topics.
 *
 * Returns the connection state plus the most recent events, newest last. Events are
 * kept in a bounded buffer so a chatty topic cannot grow the array without limit.
 */
export function useEventStream(
  topics: StreamTopic[],
  { enabled = true, limit = 50, onEvent }: { enabled?: boolean; limit?: number; onEvent?: (event: StreamEvent) => void } = {},
) {
  const [state, setState] = useState<ConnectionState>('closed')
  const [events, setEvents] = useState<StreamEvent[]>([])
  const onEventRef = useRef(onEvent)
  onEventRef.current = onEvent

  // Serialised so a caller passing a new array literal on every render does not
  // reconnect on every render.
  const key = topics.join(',')

  useEffect(() => {
    if (!enabled || !key) {
      setState('closed')
      return
    }
    const wanted = key.split(',') as StreamTopic[]
    let source: EventSource | null = null
    let retry: ReturnType<typeof setTimeout> | null = null
    let closed = false
    let attempt = 0

    const push = (event: StreamEvent) => {
      setEvents((previous) => [...previous, event].slice(-limit))
      onEventRef.current?.(event)
    }

    const connect = () => {
      if (closed) return
      setState('connecting')
      source = new EventSource(streamUrl(wanted))

      source.onopen = () => {
        attempt = 0
        setState('open')
      }

      source.onmessage = (message) => {
        try {
          push(JSON.parse(message.data) as StreamEvent)
        } catch {
          // A malformed frame must not tear down a working connection.
        }
      }

      // Named events arrive on their own listener rather than onmessage.
      for (const topic of wanted) {
        source.addEventListener(topic, (message) => {
          try {
            push({ ...(JSON.parse((message as MessageEvent).data) as StreamEvent), topic })
          } catch {
            /* ignore a malformed frame */
          }
        })
      }

      source.onerror = () => {
        source?.close()
        if (closed) return
        setState('error')
        // Exponential backoff, capped, so a server restart does not get hammered.
        attempt += 1
        const delay = Math.min(1000 * 2 ** (attempt - 1), 15_000)
        retry = setTimeout(connect, delay)
      }
    }

    connect()

    return () => {
      closed = true
      if (retry) clearTimeout(retry)
      source?.close()
      setState('closed')
    }
  }, [key, enabled, limit])

  return { state, events, latest: events[events.length - 1] }
}

/**
 * One-shot JSON poll of the same figures the stream pushes, for the first paint.
 *
 * The stream only carries deltas, so a freshly opened screen still needs a snapshot or
 * it would sit empty until the next event.
 */
export function useStreamSnapshot(days = 1, enabled = true) {
  const [snapshot, setSnapshot] = useState<Record<string, unknown> | null>(null)

  useEffect(() => {
    if (!enabled) return
    let cancelled = false
    const token = tokenStore.get()
    const headers: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {}

    fetch(`${API_BASE}/stream/snapshot?days=${days}`, { headers })
      .then((response) => (response.ok ? response.json() : null))
      .then((payload) => {
        if (!cancelled && payload) setSnapshot(payload)
      })
      .catch(() => {
        /* the screen falls back to its normal query */
      })

    return () => {
      cancelled = true
    }
  }, [days, enabled])

  return snapshot
}

/** Track a background job, polling until it finishes. */
export function useJob(jobKey: string | null, { enabled = true }: { enabled?: boolean } = {}) {
  const [job, setJob] = useState<Record<string, unknown> | null>(null)
  const [events, setEvents] = useState<Array<Record<string, unknown>>>([])
  const [loading, setLoading] = useState(Boolean(jobKey))

  useEffect(() => {
    if (!jobKey || !enabled) return
    let cancelled = false
    let timer: ReturnType<typeof setTimeout> | null = null
    const token = tokenStore.get()
    const headers: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {}
    const terminal = ['succeeded', 'failed', 'cancelled']

    const poll = async () => {
      try {
        const response = await fetch(`${API_BASE}/jobs/${jobKey}`, { headers })
        if (!response.ok) {
          if (!cancelled) setLoading(false)
          return
        }
        const payload = await response.json()
        if (cancelled) return
        setJob(payload)
        setEvents(payload.events ?? [])
        const status = String(payload.status ?? '')
        if (terminal.includes(status)) {
          setLoading(false)
          return
        }
      } catch {
        // A transient failure just means the next poll is a little later.
      }
      if (!cancelled) timer = setTimeout(poll, 1500)
    }

    void poll()
    return () => {
      cancelled = true
      if (timer) clearTimeout(timer)
    }
  }, [jobKey, enabled])

  return { job, events, loading }
}
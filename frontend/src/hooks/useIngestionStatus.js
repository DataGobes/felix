import { useState, useEffect, useRef, useCallback } from 'react'
import { getIngestionStatus, INGESTION_STREAM_URL } from '../api/client'

/**
 * Hook that tracks ingestion pipeline jobs via SSE with REST polling fallback.
 *
 * - Connects to /ingestion/stream for real-time updates
 * - Falls back to polling /ingestion/status every 3s if SSE fails
 * - Dispatches 'ingestion-complete' CustomEvent when a job finishes
 * - Returns { jobs, connected } where connected indicates SSE is live
 */
export function useIngestionStatus() {
  const [jobs, setJobs] = useState([])
  const [connected, setConnected] = useState(false)
  const prevJobsRef = useRef(new Map())
  const eventSourceRef = useRef(null)
  const pollIntervalRef = useRef(null)
  const sseRetryTimeoutRef = useRef(null)

  // Detect newly completed jobs and dispatch custom events
  const detectCompletions = useCallback((newJobs) => {
    const prevMap = prevJobsRef.current
    for (const job of newJobs) {
      const prev = prevMap.get(job.id)
      if (prev && prev.status !== 'completed' && job.status === 'completed') {
        window.dispatchEvent(new CustomEvent('ingestion-complete', { detail: job }))
      }
    }
    prevJobsRef.current = new Map(newJobs.map(j => [j.id, j]))
  }, [])

  const handleJobs = useCallback((newJobs) => {
    if (!Array.isArray(newJobs)) return
    detectCompletions(newJobs)
    setJobs(newJobs)
  }, [detectCompletions])

  // REST polling fallback
  const startPolling = useCallback(() => {
    if (pollIntervalRef.current) return
    pollIntervalRef.current = setInterval(async () => {
      try {
        const data = await getIngestionStatus()
        handleJobs(data)
      } catch {
        // Silently retry next interval
      }
    }, 3000)
  }, [handleJobs])

  const stopPolling = useCallback(() => {
    if (pollIntervalRef.current) {
      clearInterval(pollIntervalRef.current)
      pollIntervalRef.current = null
    }
  }, [])

  // SSE connection
  const connectSSE = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close()
    }

    const es = new EventSource(INGESTION_STREAM_URL)
    eventSourceRef.current = es

    es.onopen = () => {
      setConnected(true)
      stopPolling() // SSE is live, stop polling
    }

    es.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        if (data.error) {
          console.warn('SSE error from server:', data.error)
          return
        }
        handleJobs(data)
      } catch {
        // Ignore parse errors (keepalive comments, etc.)
      }
    }

    es.onerror = () => {
      setConnected(false)
      es.close()
      eventSourceRef.current = null

      // Start REST polling as fallback
      startPolling()

      // Retry SSE after 10 seconds
      sseRetryTimeoutRef.current = setTimeout(connectSSE, 10000)
    }
  }, [handleJobs, startPolling, stopPolling])

  useEffect(() => {
    // Do an initial REST fetch, then connect SSE
    getIngestionStatus()
      .then(handleJobs)
      .catch(() => {})

    connectSSE()

    return () => {
      if (eventSourceRef.current) eventSourceRef.current.close()
      stopPolling()
      if (sseRetryTimeoutRef.current) clearTimeout(sseRetryTimeoutRef.current)
    }
  }, [connectSSE, handleJobs, stopPolling])

  return { jobs, connected }
}

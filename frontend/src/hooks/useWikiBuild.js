import { useCallback, useEffect, useRef, useState } from 'react'
import { wikiStreamUrl, getWikiStatus } from '../api/client'

export default function useWikiBuild(indexSlug) {
  const [job, setJob] = useState(null)
  const [connected, setConnected] = useState(false)
  const esRef = useRef(null)

  const connect = useCallback(() => {
    if (!indexSlug) return
    if (esRef.current) esRef.current.close()
    const es = new EventSource(wikiStreamUrl(indexSlug))
    esRef.current = es
    es.onopen = () => setConnected(true)
    es.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        if (data.error) return
        setJob(data)
      } catch { /* keepalive */ }
    }
    es.onerror = () => {
      setConnected(false)
      es.close()
      esRef.current = null
    }
  }, [indexSlug])

  useEffect(() => {
    if (!indexSlug) return
    getWikiStatus(indexSlug).then(setJob).catch(() => {})
    connect()
    return () => { if (esRef.current) esRef.current.close() }
  }, [indexSlug, connect])

  return { job, connected, reconnect: connect }
}

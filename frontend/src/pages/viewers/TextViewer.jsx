import { useState, useEffect, useCallback } from 'react'
import {
  getChunks,
  getChunk,
  getChunkTables,
  getChunkImages,
} from '../../api/client'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import TreeRow from './shared/TreeRow'
import ChunkDetail from './shared/ChunkDetail'

function truncate(str, len = 50) {
  if (!str) return ''
  return str.length > len ? str.slice(0, len) + '…' : str
}

export default function TextViewer({ documentId }) {
  const [chunks, setChunks] = useState([])
  const [loading, setLoading] = useState(true)

  const [selected, setSelected] = useState(null)
  const [chunkDetail, setChunkDetail] = useState(null)
  const [chunkTables, setChunkTables] = useState([])
  const [chunkImages, setChunkImages] = useState([])
  const [detailLoading, setDetailLoading] = useState(false)

  useEffect(() => {
    let cancelled = false
    const fetchAll = async () => {
      setLoading(true)
      try {
        const c = await getChunks(documentId)
        if (cancelled) return
        const cArr = c?.chunks ?? c
        setChunks(Array.isArray(cArr) ? cArr : [])
      } catch (e) {
        console.error('Failed to load document:', e)
      }
      if (!cancelled) setLoading(false)
    }
    fetchAll()
    return () => { cancelled = true }
  }, [documentId])

  const selectChunk = useCallback(async (ch) => {
    setSelected({ type: 'chunk', id: `ch-${ch.chunk_id}`, chunkId: ch.chunk_id, data: ch })
    setDetailLoading(true)
    try {
      const [detail, t, i] = await Promise.all([
        getChunk(ch.chunk_id),
        getChunkTables(ch.chunk_id),
        getChunkImages(ch.chunk_id),
      ])
      setChunkDetail(detail)
      const tArr = t?.tables ?? t
      setChunkTables(Array.isArray(tArr) ? tArr : [])
      const iArr = i?.images ?? i
      setChunkImages(Array.isArray(iArr) ? iArr : [])
    } catch (e) {
      console.error('Failed to load chunk detail:', e)
    }
    setDetailLoading(false)
  }, [])

  const selectAll = useCallback(() => {
    setSelected({ type: 'all', id: 'all' })
    setChunkDetail(null)
    setChunkTables([])
    setChunkImages([])
  }, [])

  const renderDetail = () => {
    if (!selected) {
      return (
        <div className="h-full flex items-center justify-center">
          <p className="text-sm text-warm-500">Select a chunk or view all content</p>
        </div>
      )
    }

    if (selected.type === 'all') {
      // Show all chunks sequentially with visual boundaries
      return (
        <div className="p-5 space-y-0">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-warm-900">Full Document</h2>
            <Badge variant="outline" className="text-warm-600 border-warm-200 text-xs">
              {chunks.length} chunks · {chunks.reduce((s, c) => s + (c.token_count || 0), 0)} tokens
            </Badge>
          </div>
          {chunks
            .sort((a, b) => a.chunk_index - b.chunk_index)
            .map((ch, i) => (
              <div
                key={ch.chunk_id}
                className={`p-4 text-sm text-warm-900 whitespace-pre-wrap leading-relaxed ${
                  i % 2 === 0
                    ? 'bg-warm-100 border-l-2 border-warm-200'
                    : 'bg-warm-100 border-l-2 border-warm-200'
                }`}
              >
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-[10px] text-warm-500 font-mono">
                    chunk {ch.chunk_index}
                  </span>
                  <span className="text-[10px] text-warm-400">
                    {ch.token_count} tok
                  </span>
                </div>
                {ch.content}
              </div>
            ))}
        </div>
      )
    }

    return (
      <ChunkDetail
        chunk={chunkDetail || selected.data}
        tables={chunkTables}
        images={chunkImages}
        loading={detailLoading}
      />
    )
  }

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <p className="text-warm-500">Loading text document…</p>
      </div>
    )
  }

  const totalTokens = chunks.reduce((s, c) => s + (c.token_count || 0), 0)

  return (
    <div className="flex-1 grid grid-cols-[320px_minmax(0,1fr)] min-h-0">
      <aside className="border-r border-warm-200 flex flex-col min-h-0">
        <div className="px-4 py-2.5 border-b border-warm-200">
          <h2 className="text-xs font-medium text-warm-600 uppercase tracking-wider">Chunks</h2>
        </div>
        <ScrollArea className="flex-1">
          <div className="py-1">
            <TreeRow
              depth={0}
              icon="◇"
              label="View All"
              meta={`${totalTokens} tok`}
              selected={selected?.id === 'all'}
              onClick={selectAll}
            />
            <TreeRow depth={0} label={`── ${chunks.length} Chunks ──`} dimmed />
            {chunks
              .sort((a, b) => a.chunk_index - b.chunk_index)
              .map(ch => (
                <TreeRow
                  key={ch.chunk_id}
                  depth={0}
                  icon="◆"
                  label={truncate(ch.content, 40)}
                  meta={`${ch.token_count} tok`}
                  selected={selected?.id === `ch-${ch.chunk_id}`}
                  onClick={() => selectChunk(ch)}
                />
              ))}

            {chunks.length === 0 && (
              <p className="text-xs text-warm-500 px-4 py-2">No chunks found</p>
            )}
          </div>
        </ScrollArea>
      </aside>

      <main className="flex flex-col min-h-0">
        <div className="px-4 py-2.5 border-b border-warm-200">
          <h2 className="text-xs font-medium text-warm-600 uppercase tracking-wider">
            {selected
              ? selected.type === 'all' ? 'Full Document'
              : selected.type === 'chunk' ? 'Chunk Detail'
              : 'Detail'
              : 'Detail'}
          </h2>
        </div>
        <ScrollArea className="flex-1">
          {renderDetail()}
        </ScrollArea>
      </main>
    </div>
  )
}

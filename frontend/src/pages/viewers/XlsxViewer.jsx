import { useState, useEffect, useCallback } from 'react'
import {
  getDocumentPages,
  getDocumentTables,
  getChunks,
  getChunk,
  getChunkTables,
  getChunkImages,
} from '../../api/client'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import TreeRow from './shared/TreeRow'
import TableRenderer from './shared/TableRenderer'
import ChunkDetail from './shared/ChunkDetail'

function truncate(str, len = 50) {
  if (!str) return ''
  return str.length > len ? str.slice(0, len) + '…' : str
}

export default function XlsxViewer({ documentId }) {
  const [pages, setPages] = useState([])
  const [tables, setTables] = useState([])
  const [chunks, setChunks] = useState([])
  const [loading, setLoading] = useState(true)

  const [selected, setSelected] = useState(null)
  const [expanded, setExpanded] = useState(new Set())

  const [chunkDetail, setChunkDetail] = useState(null)
  const [chunkTables, setChunkTables] = useState([])
  const [chunkImages, setChunkImages] = useState([])
  const [detailLoading, setDetailLoading] = useState(false)

  useEffect(() => {
    let cancelled = false
    const fetchAll = async () => {
      setLoading(true)
      try {
        const [p, t, c] = await Promise.all([
          getDocumentPages(documentId),
          getDocumentTables(documentId),
          getChunks(documentId),
        ])
        if (cancelled) return
        const pArr = p?.pages ?? p
        setPages(Array.isArray(pArr) ? pArr : [])
        const tArr = t?.tables ?? t
        setTables(Array.isArray(tArr) ? tArr : [])
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

  // Group tables by page (sheet)
  const tablesByPage = {}
  for (const t of tables) {
    ;(tablesByPage[t.page_number] ??= []).push(t)
  }

  const selectSheet = useCallback((page) => {
    setSelected({ type: 'sheet', id: `sheet-${page.page_number}`, data: page, pageNumber: page.page_number })
    setChunkDetail(null)
  }, [])

  const selectTable = useCallback((table) => {
    setSelected({ type: 'table', id: `table-${table.table_id}`, data: table })
    setChunkDetail(null)
  }, [])

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

  const toggle = useCallback((nodeId) => {
    setExpanded(prev => {
      const next = new Set(prev)
      if (next.has(nodeId)) next.delete(nodeId)
      else next.add(nodeId)
      return next
    })
  }, [])

  const renderDetail = () => {
    if (!selected) {
      return (
        <div className="h-full flex items-center justify-center">
          <p className="text-sm text-warm-500">Select a sheet or table to view</p>
        </div>
      )
    }

    if (selected.type === 'chunk') {
      return (
        <ChunkDetail
          chunk={chunkDetail || selected.data}
          tables={chunkTables}
          images={chunkImages}
          loading={detailLoading}
        />
      )
    }

    if (selected.type === 'table') {
      const table = selected.data
      return (
        <div className="p-5 space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold text-warm-900">
              {table.caption || `Table ${table.table_id}`}
            </h2>
            <div className="flex gap-2">
              {table.num_rows != null && table.num_cols != null && (
                <Badge variant="outline" className="text-warm-600 border-warm-200 text-xs">
                  {table.num_rows} rows × {table.num_cols} cols
                </Badge>
              )}
              <Badge variant="outline" className="text-warm-500 border-warm-200 text-xs">
                Sheet {table.page_number}
              </Badge>
            </div>
          </div>
          <TableRenderer table={table} />
        </div>
      )
    }

    // Sheet overview — show all tables for this sheet
    const page = selected.data
    const sheetTables = tablesByPage[page.page_number] || []

    return (
      <div className="p-5 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-warm-900">Sheet {page.page_number}</h2>
          <div className="flex gap-2">
            {page.element_count && (
              <Badge variant="outline" className="text-warm-600 border-warm-200 text-xs">
                {page.element_count} elements
              </Badge>
            )}
            <Badge variant="outline" className="text-warm-600 border-warm-600/30 text-xs">
              {sheetTables.length} tables
            </Badge>
          </div>
        </div>

        {sheetTables.length > 0 ? (
          <div className="space-y-4">
            {sheetTables.map(table => (
              <div key={table.table_id}>
                {table.caption && (
                  <p className="text-xs font-medium text-warm-500 uppercase tracking-wider mb-2">
                    {table.caption}
                  </p>
                )}
                <TableRenderer table={table} />
              </div>
            ))}
          </div>
        ) : (
          <p className="text-sm text-warm-500">No tables found on this sheet</p>
        )}
      </div>
    )
  }

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <p className="text-warm-500">Loading spreadsheet…</p>
      </div>
    )
  }

  return (
    <div className="flex-1 grid grid-cols-[320px_minmax(0,1fr)] min-h-0">
      <aside className="border-r border-warm-200 flex flex-col min-h-0">
        <div className="px-4 py-2.5 border-b border-warm-200">
          <h2 className="text-xs font-medium text-warm-600 uppercase tracking-wider">Sheets</h2>
        </div>
        <ScrollArea className="flex-1">
          <div className="py-1">
            {pages
              .sort((a, b) => a.page_number - b.page_number)
              .map(page => {
                const nid = `sheet-${page.page_number}`
                const isExp = expanded.has(nid)
                const sheetTables = tablesByPage[page.page_number] || []
                const parts = []
                if (sheetTables.length) parts.push(`${sheetTables.length} tbl`)
                if (page.element_count) parts.push(`${page.element_count} el`)

                return (
                  <div key={nid}>
                    <TreeRow
                      depth={0}
                      icon={isExp ? '▾' : '▸'}
                      label={`Sheet ${page.page_number}`}
                      meta={parts.join(' · ') || null}
                      selected={selected?.id === nid}
                      onClick={() => {
                        toggle(nid)
                        selectSheet(page)
                      }}
                    />
                    {isExp && sheetTables.map(table => (
                      <TreeRow
                        key={table.table_id}
                        depth={1}
                        icon="▦"
                        label={table.caption || `Table ${table.table_id}`}
                        meta={table.num_rows != null ? `${table.num_rows}×${table.num_cols}` : null}
                        selected={selected?.id === `table-${table.table_id}`}
                        onClick={() => selectTable(table)}
                      />
                    ))}
                  </div>
                )
              })}

            {/* Chunks */}
            {chunks.length > 0 && (
              <>
                <TreeRow depth={0} label={`── Chunks (${chunks.length}) ──`} dimmed />
                {chunks.map(ch => (
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
              </>
            )}

            {pages.length === 0 && (
              <p className="text-xs text-warm-500 px-4 py-2">No sheets found</p>
            )}
          </div>
        </ScrollArea>
      </aside>

      <main className="flex flex-col min-h-0 min-w-0">
        <div className="px-4 py-2.5 border-b border-warm-200">
          <h2 className="text-xs font-medium text-warm-600 uppercase tracking-wider">
            {selected
              ? selected.type === 'sheet' ? 'Sheet Overview'
              : selected.type === 'table' ? 'Table View'
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

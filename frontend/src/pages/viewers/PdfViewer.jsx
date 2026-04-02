import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import {
  getDocumentStructure,
  getDocumentPages,
  getChunks,
  getChunk,
  getChunkTables,
  getChunkImages,
  getPageElements,
  getImageUrl,
} from '../../api/client'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import TreeRow from './shared/TreeRow'
import ElementRenderer from './shared/ElementRenderer'
import ChunkDetail from './shared/ChunkDetail'
import GraphView from './shared/GraphView'
import GraphDetailOverlay from './shared/GraphDetailOverlay'

function truncate(str, len = 50) {
  if (!str) return ''
  return str.length > len ? str.slice(0, len) + '…' : str
}

function codePreview(el) {
  let text = el.full_text || el.text_preview || ''
  const lang = el.metadata?.code_language
  if (lang) {
    const firstLine = text.split('\n', 1)[0].trim().toLowerCase()
    if (firstLine === lang.toLowerCase()) text = text.slice(text.indexOf('\n') + 1)
  }
  return truncate(text.trim(), 45)
}

function elementIcon(type) {
  switch (type) {
    case 'section_header': return '§'
    case 'text': return '¶'
    case 'paragraph': return '¶'
    case 'list_item': return '•'
    case 'code': return '⟨⟩'
    case 'formula': return '∑'
    case 'picture': return '▣'
    case 'caption': return 'ⓘ'
    case 'footnote': return '†'
    case 'page_header':
    case 'page_footer': return '─'
    default: return '·'
  }
}

function buildHeadingTree(structure) {
  if (!structure?.length) return []
  const sorted = [...structure].sort(
    (a, b) => a.page_number - b.page_number || (a.reading_order ?? 0) - (b.reading_order ?? 0),
  )
  const root = []
  const stack = [{ level: 0, children: root }]

  sorted.forEach((h, i) => {
    const node = {
      id: `h-${i}`,
      text: h.heading_text,
      level: h.heading_level,
      pageNumber: h.page_number,
      subHeadings: [],
    }
    while (stack.length > 1 && stack[stack.length - 1].level >= h.heading_level) {
      stack.pop()
    }
    stack[stack.length - 1].children.push(node)
    stack.push({ level: h.heading_level, children: node.subHeadings })
  })

  return root
}

function assignPagesToHeadings(tree, pages) {
  const flat = []
  function walk(nodes) {
    for (const n of nodes) {
      flat.push(n)
      walk(n.subHeadings)
    }
  }
  walk(tree)

  const byHeading = {}
  const orphans = []

  for (const page of [...pages].sort((a, b) => a.page_number - b.page_number)) {
    let best = null
    for (const h of flat) {
      if (h.pageNumber <= page.page_number) best = h
      else break
    }
    if (best) {
      ;(byHeading[best.id] ??= []).push(page)
    } else {
      orphans.push(page)
    }
  }

  return { byHeading, orphans }
}

function collectSectionPages(heading, byHeading) {
  const direct = byHeading[heading.id] || []
  const nested = heading.subHeadings.flatMap(sub => collectSectionPages(sub, byHeading))
  return [...direct, ...nested]
}

export default function PdfViewer({ documentId }) {
  const [structure, setStructure] = useState([])
  const [pages, setPages] = useState([])
  const [chunks, setChunks] = useState([])
  const [loading, setLoading] = useState(true)

  const [expanded, setExpanded] = useState(new Set())
  const [selected, setSelected] = useState(null)

  const [elementsCache, setElementsCache] = useState({})
  const elementsCacheRef = useRef({})
  const loadingPagesRef = useRef(new Set())
  const [loadingPages, setLoadingPages] = useState(new Set())

  const [viewMode, setViewMode] = useState('tree')

  const [chunkDetail, setChunkDetail] = useState(null)
  const [chunkTables, setChunkTables] = useState([])
  const [chunkImages, setChunkImages] = useState([])
  const [detailLoading, setDetailLoading] = useState(false)

  useEffect(() => {
    let cancelled = false
    const fetchAll = async () => {
      setLoading(true)
      try {
        const [s, p, c] = await Promise.all([
          getDocumentStructure(documentId),
          getDocumentPages(documentId),
          getChunks(documentId),
        ])
        if (cancelled) return
        setStructure(Array.isArray(s) ? s : [])
        const pArr = p?.pages ?? p
        setPages(Array.isArray(pArr) ? pArr : [])
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

  const headingTree = useMemo(() => buildHeadingTree(structure), [structure])

  const { byHeading, orphans } = useMemo(
    () => assignPagesToHeadings(headingTree, pages),
    [headingTree, pages],
  )

  // Map chunks to pages — use page_numbers array when available for multi-page chunks
  const chunksByPage = useMemo(() => {
    const map = {}
    for (const ch of chunks) {
      const pageNumbers = ch.page_numbers ?? [ch.page_number ?? 0]
      for (const pn of pageNumbers) {
        ;(map[pn] ??= []).push(ch)
      }
    }
    for (const pn in map) {
      // Deduplicate (a chunk may appear once per page it spans)
      const seen = new Set()
      map[pn] = map[pn].filter(ch => {
        if (seen.has(ch.chunk_id)) return false
        seen.add(ch.chunk_id)
        return true
      })
      map[pn].sort((a, b) => a.chunk_index - b.chunk_index)
    }
    return map
  }, [chunks])

  const fetchElements = useCallback(async (pageId, pageNumber) => {
    if (elementsCacheRef.current[pageNumber] || loadingPagesRef.current.has(pageNumber)) return
    loadingPagesRef.current.add(pageNumber)
    setLoadingPages(new Set(loadingPagesRef.current))
    try {
      const data = await getPageElements(pageId, { includeText: true })
      const els = Array.isArray(data) ? data : (data?.elements ?? [])
      elementsCacheRef.current[pageNumber] = els
      setElementsCache({ ...elementsCacheRef.current })
    } catch (e) {
      console.error(`Failed to load elements for page ${pageNumber}:`, e)
      elementsCacheRef.current[pageNumber] = []
      setElementsCache({ ...elementsCacheRef.current })
    }
    loadingPagesRef.current.delete(pageNumber)
    setLoadingPages(new Set(loadingPagesRef.current))
  }, [])

  const toggle = useCallback((nodeId, pageId, pageNumber) => {
    setExpanded(prev => {
      const next = new Set(prev)
      if (next.has(nodeId)) next.delete(nodeId)
      else {
        next.add(nodeId)
        if (pageId != null) fetchElements(pageId, pageNumber)
      }
      return next
    })
  }, [fetchElements])

  const select = useCallback(async (node) => {
    setSelected(node)
    setChunkDetail(null)
    setChunkTables([])
    setChunkImages([])

    if (node.type === 'page') {
      fetchElements(node.pageId, node.pageNumber)
    } else if (node.type === 'chunk') {
      setDetailLoading(true)
      try {
        const [detail, tables, images] = await Promise.all([
          getChunk(node.chunkId),
          getChunkTables(node.chunkId),
          getChunkImages(node.chunkId),
        ])
        setChunkDetail(detail)
        const t = tables?.tables ?? tables
        setChunkTables(Array.isArray(t) ? t : [])
        const i = images?.images ?? images
        setChunkImages(Array.isArray(i) ? i : [])
      } catch (e) {
        console.error('Failed to load chunk detail:', e)
      }
      setDetailLoading(false)
    }
  }, [fetchElements])

  /* ─────── Tree rendering ─────── */

  const renderHeading = (heading, depth) => {
    const isExp = expanded.has(heading.id)
    const directPages = byHeading[heading.id] || []
    const allPages = collectSectionPages(heading, byHeading)
    const hasContent = allPages.length > 0 || heading.subHeadings.length > 0
    if (!hasContent) return null

    return (
      <div key={heading.id}>
        <TreeRow
          depth={depth}
          icon={isExp ? '▾' : '▸'}
          label={heading.text}
          meta={`p.${heading.pageNumber}`}
          selected={selected?.id === heading.id}
          onClick={() => {
            toggle(heading.id)
            select({ type: 'heading', id: heading.id, data: heading })
          }}
        />
        {isExp && (
          <>
            {heading.subHeadings.map(sub => renderHeading(sub, depth + 1))}
            {directPages
              .sort((a, b) => a.page_number - b.page_number)
              .map(page => renderPage(page, depth + 1))}
          </>
        )}
      </div>
    )
  }

  const renderPage = (page, depth) => {
    const nid = `page-${page.page_number}`
    const isExp = expanded.has(nid)
    const els = elementsCache[page.page_number]
    const pChunks = chunksByPage[page.page_number] || []
    const isLoadingEls = loadingPages.has(page.page_number)

    // BUG FIX: Always use page.element_count for tree badge (stable value from DB).
    // Only filter to body layer in the detail pane and expanded element list.
    const parts = []
    if (page.element_count) parts.push(`${page.element_count} el`)
    if (pChunks.length) parts.push(`${pChunks.length} ch`)

    return (
      <div key={nid}>
        <TreeRow
          depth={depth}
          icon={isExp ? '▾' : '▸'}
          label={`Page ${page.page_number}`}
          meta={parts.join(' · ') || null}
          selected={selected?.id === nid}
          onClick={() => {
            toggle(nid, page.page_id, page.page_number)
            select({
              type: 'page', id: nid,
              pageId: page.page_id,
              pageNumber: page.page_number,
              data: page,
            })
          }}
        />
        {isExp && (
          <>
            {isLoadingEls && (
              <TreeRow depth={depth + 1} label="Loading…" dimmed />
            )}
            {els
              ?.filter(el => el.content_layer === 'body' && (el.full_text || el.text_preview || el.element_type === 'picture'))
              .sort((a, b) => a.reading_order - b.reading_order)
              .map((el) => (
                <TreeRow
                  key={el.element_id}
                  depth={depth + 1}
                  icon={elementIcon(el.element_type)}
                  label={
                    el.element_type === 'picture'
                      ? 'Image'
                      : el.element_type === 'code'
                      ? codePreview(el)
                      : truncate(el.full_text || el.text_preview, 45)
                  }
                  selected={selected?.id === `el-${el.element_id}`}
                  onClick={() => select({
                    type: 'element',
                    id: `el-${el.element_id}`,
                    data: el,
                    pageNumber: page.page_number,
                  })}
                />
              ))}
            {pChunks.length > 0 && (
              <>
                <TreeRow depth={depth + 1} label={`── Chunks (${pChunks.length}) ──`} dimmed />
                {pChunks.map(ch => (
                  <TreeRow
                    key={ch.chunk_id}
                    depth={depth + 1}
                    icon="◆"
                    label={truncate(ch.content, 40)}
                    meta={`${ch.token_count} tok`}
                    selected={selected?.id === `ch-${ch.chunk_id}`}
                    onClick={() => select({
                      type: 'chunk',
                      id: `ch-${ch.chunk_id}`,
                      chunkId: ch.chunk_id,
                      data: ch,
                    })}
                  />
                ))}
              </>
            )}
          </>
        )}
      </div>
    )
  }

  /* ─────── Detail rendering ─────── */

  const renderDetail = () => {
    if (!selected) {
      return (
        <div className="h-full flex items-center justify-center">
          <p className="text-sm text-warm-500">Select an item to view details</p>
        </div>
      )
    }

    switch (selected.type) {
      case 'heading': {
        const h = selected.data
        const sectionPages = collectSectionPages(h, byHeading)
        let totalChunks = 0
        for (const p of sectionPages) totalChunks += (chunksByPage[p.page_number] || []).length

        return (
          <div className="p-5 space-y-5">
            <div>
              <p className="text-xs font-medium text-warm-500 uppercase tracking-wider mb-1">Section</p>
              <h2 className="text-xl font-semibold text-warm-900">{h.text}</h2>
            </div>
            <div className="flex flex-wrap gap-2">
              <Badge variant="outline" className="text-warm-600 border-warm-200 text-xs">
                {sectionPages.length} pages
              </Badge>
              <Badge variant="outline" className="text-ember border-ember/30 text-xs">
                {totalChunks} chunks
              </Badge>
              <Badge variant="outline" className="text-warm-500 border-warm-200 text-xs">
                Level {h.level}
              </Badge>
            </div>
            {h.subHeadings.length > 0 && (
              <div className="space-y-1">
                <p className="text-xs font-medium text-warm-500 uppercase tracking-wider">Sub-sections</p>
                {h.subHeadings.map(sub => (
                  <p key={sub.id} className="text-sm text-warm-900 pl-3">
                    {sub.text} <span className="text-warm-400">p.{sub.pageNumber}</span>
                  </p>
                ))}
              </div>
            )}
          </div>
        )
      }

      case 'page': {
        const page = selected.data
        const els = elementsCache[selected.pageNumber]
        const isLoading = loadingPages.has(selected.pageNumber)

        return (
          <div className="p-5 space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold text-warm-900">Page {page.page_number}</h2>
              <div className="flex gap-2">
                {page.width && page.height && (
                  <Badge variant="outline" className="text-warm-500 border-warm-200 text-xs">
                    {Math.round(page.width)} × {Math.round(page.height)}
                  </Badge>
                )}
                {els && (
                  <Badge variant="outline" className="text-warm-600 border-warm-200 text-xs">
                    {els.filter(e => e.content_layer === 'body').length} body elements
                  </Badge>
                )}
              </div>
            </div>
            {isLoading && <p className="text-sm text-warm-500">Loading page content…</p>}
            {els && (
              <div className="p-5 bg-warm-100 rounded-xl border border-warm-200">
                {els
                  .filter(e => e.content_layer === 'body')
                  .sort((a, b) => a.reading_order - b.reading_order)
                  .map((el, i) => (
                    <ElementRenderer key={el.element_id || i} element={el} />
                  ))}
                {els.filter(e => e.content_layer === 'body').length === 0 && (
                  <p className="text-sm text-warm-500">No body elements on this page</p>
                )}
              </div>
            )}
          </div>
        )
      }

      case 'element': {
        const el = selected.data
        const text = el.full_text || el.text_preview || ''

        return (
          <div className="p-5 space-y-4">
            <div>
              <p className="text-xs font-medium text-warm-500 uppercase tracking-wider mb-1">Element</p>
              <div className="flex flex-wrap gap-2">
                <Badge variant="outline" className="text-ember border-ember/30 text-xs">
                  {el.element_type}
                </Badge>
                {selected.pageNumber && (
                  <Badge variant="outline" className="text-warm-500 border-warm-200 text-xs">
                    page {selected.pageNumber}
                  </Badge>
                )}
                <Badge variant="outline" className="text-warm-500 border-warm-200 text-xs">
                  order {el.reading_order}
                </Badge>
                {el.heading_level && (
                  <Badge variant="outline" className="text-warm-600 border-warm-600/30 text-xs">
                    H{el.heading_level}
                  </Badge>
                )}
                {el.metadata?.code_language && (
                  <Badge variant="outline" className="text-amber-400 border-amber-800 text-xs">
                    {el.metadata.code_language}
                  </Badge>
                )}
              </div>
            </div>

            {text && (
              <div className="space-y-1">
                <p className="text-xs font-medium text-warm-500 uppercase tracking-wider">Content</p>
                {el.element_type === 'code' || el.element_type === 'formula' ? (
                  <ElementRenderer element={el} />
                ) : (
                  <div className="p-4 bg-warm-100 rounded-lg border border-warm-200 text-sm text-warm-900 whitespace-pre-wrap leading-relaxed">
                    {text}
                  </div>
                )}
              </div>
            )}

            {el.element_type === 'picture' && (
              <div className="space-y-1">
                <p className="text-xs font-medium text-warm-500 uppercase tracking-wider">Image</p>
                <div className="py-8 border border-dashed border-warm-200 rounded-lg text-sm text-warm-500 text-center bg-warm-100/30">
                  ▣ No direct image preview — view via chunk detail
                </div>
              </div>
            )}

            {el.bbox_left != null && (
              <div className="space-y-1">
                <p className="text-xs font-medium text-warm-500 uppercase tracking-wider">Position</p>
                <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-warm-600">
                  <span>Left: {el.bbox_left?.toFixed(1)}</span>
                  <span>Top: {el.bbox_top?.toFixed(1)}</span>
                  <span>Right: {el.bbox_right?.toFixed(1)}</span>
                  <span>Bottom: {el.bbox_bottom?.toFixed(1)}</span>
                  <span>Width: {(el.bbox_right - el.bbox_left)?.toFixed(1)}</span>
                  <span>Height: {Math.abs(el.bbox_top - el.bbox_bottom)?.toFixed(1)}</span>
                </div>
              </div>
            )}
          </div>
        )
      }

      case 'chunk':
        return (
          <ChunkDetail
            chunk={chunkDetail || selected.data}
            tables={chunkTables}
            images={chunkImages}
            loading={detailLoading}
          />
        )

      default:
        return null
    }
  }

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <p className="text-warm-500">Loading document…</p>
      </div>
    )
  }

  const detailTitle = selected
    ? selected.type === 'heading' ? 'Section Overview'
    : selected.type === 'page' ? 'Page View'
    : selected.type === 'element' ? 'Element Detail'
    : selected.type === 'chunk' ? 'Chunk Detail'
    : 'Detail'
    : 'Detail'

  const viewToggle = (
    <div className="flex gap-1">
      {['tree', 'graph'].map(mode => (
        <button
          key={mode}
          onClick={() => setViewMode(mode)}
          className={`px-2.5 py-0.5 text-[10px] uppercase tracking-wider rounded transition-colors ${
            viewMode === mode
              ? 'bg-ember/[0.08] text-ember'
              : 'text-warm-500 hover:text-warm-600'
          }`}
        >
          {mode}
        </button>
      ))}
    </div>
  )

  if (viewMode === 'graph') {
    return (
      <div className="flex-1 flex flex-col min-h-0">
        <div className="px-4 py-2.5 border-b border-warm-200 flex items-center justify-between shrink-0">
          <h2 className="text-xs font-medium text-warm-600 uppercase tracking-wider">Graph</h2>
          {viewToggle}
        </div>
        <div className="flex-1 relative min-h-0">
          <GraphView
            headingTree={headingTree}
            pages={pages}
            chunks={chunks}
            byHeading={byHeading}
            orphans={orphans}
            chunksByPage={chunksByPage}
            elementsCache={elementsCache}
            loadingPages={loadingPages}
            selected={selected}
            onSelect={select}
            onFetchElements={fetchElements}
            renderDetail={renderDetail}
          />
          <GraphDetailOverlay
            open={!!selected}
            onClose={() => setSelected(null)}
            title={detailTitle}
          >
            {renderDetail()}
          </GraphDetailOverlay>
        </div>
      </div>
    )
  }

  return (
    <div className="flex-1 grid grid-cols-[320px_minmax(0,1fr)] min-h-0">
      <aside className="border-r border-warm-200 flex flex-col min-h-0">
        <div className="px-4 py-2.5 border-b border-warm-200 flex items-center justify-between">
          <h2 className="text-xs font-medium text-warm-600 uppercase tracking-wider">Browser</h2>
          {viewToggle}
        </div>
        <ScrollArea className="flex-1">
          <div className="py-1">
            {headingTree.length > 0 ? (
              <>
                {orphans
                  .sort((a, b) => a.page_number - b.page_number)
                  .map(page => renderPage(page, 0))}
                {headingTree.map(h => renderHeading(h, 0))}
              </>
            ) : (
              pages
                .sort((a, b) => a.page_number - b.page_number)
                .map(page => renderPage(page, 0))
            )}
            {pages.length === 0 && (
              <p className="text-xs text-warm-500 px-4 py-2">No document content found</p>
            )}
          </div>
        </ScrollArea>
      </aside>

      <main className="flex flex-col min-h-0 min-w-0 overflow-hidden">
        <div className="px-4 py-2.5 border-b border-warm-200">
          <h2 className="text-xs font-medium text-warm-600 uppercase tracking-wider">
            {detailTitle}
          </h2>
        </div>
        <ScrollArea className="flex-1">
          {renderDetail()}
        </ScrollArea>
      </main>
    </div>
  )
}

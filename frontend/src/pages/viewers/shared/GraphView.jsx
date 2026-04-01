import { useState, useMemo, useRef, useCallback, useEffect } from 'react'
import { ScrollArea } from '@/components/ui/scroll-area'
import useForceLayout from './useForceLayout'

function truncate(str, len = 24) {
  if (!str) return ''
  return str.length > len ? str.slice(0, len) + '…' : str
}

function elementIcon(type) {
  switch (type) {
    case 'section_header': return '§'
    case 'text': case 'paragraph': return '¶'
    case 'list_item': return '•'
    case 'code': return '⟨⟩'
    case 'formula': return '∑'
    case 'picture': return '▣'
    case 'caption': return 'ⓘ'
    case 'footnote': return '†'
    default: return '·'
  }
}

const MAX_ELEMENTS_PER_PAGE = 8
const LARGE_DOC_THRESHOLD = 50 // pages

const NODE_CONFIG = {
  document: { size: 28, stroke: '#00ff41', sw: 2, fill: '#0a1a0a' },
  heading:  { size: 18, stroke: '#00ff41', sw: 1.5, fill: '#0a150a' },
  page:     { size: 14, stroke: '#5a8a5a', sw: 1, fill: '#0a120a' },
  element:  { size: 7,  stroke: '#3d6b3d', sw: 1, fill: '#080e08' },
  chunk:    { size: 9,  stroke: '#00e5ff', sw: 1, fill: '#0a0f14' },
}

function HexagonShape({ r, stroke, sw, fill }) {
  const pts = Array.from({ length: 6 }, (_, i) => {
    const a = (Math.PI / 3) * i - Math.PI / 2
    return `${Math.cos(a) * r},${Math.sin(a) * r}`
  }).join(' ')
  return <polygon points={pts} stroke={stroke} strokeWidth={sw} fill={fill} />
}

function DiamondShape({ r, stroke, sw, fill }) {
  return <polygon points={`0,${-r} ${r},0 0,${r} ${-r},0`} stroke={stroke} strokeWidth={sw} fill={fill} />
}

function NodeShape({ type, data }) {
  const cfg = NODE_CONFIG[type] || NODE_CONFIG.element
  const { size: r, stroke, sw, fill } = cfg
  switch (type) {
    case 'document':
      return (<g><HexagonShape r={r} stroke={stroke} sw={sw} fill={fill} />
        <text textAnchor="middle" dy="5" fill={stroke} fontSize="14" fontWeight="bold">F</text></g>)
    case 'heading':
      return (<g><circle r={r} stroke={stroke} strokeWidth={sw} fill={fill} />
        <text textAnchor="middle" dy="4" fill="#8ab88a" fontSize="11">§</text></g>)
    case 'page':
      return (<g><rect x={-r} y={-r*1.3} width={r*2} height={r*2.6} rx={3}
        stroke={stroke} strokeWidth={sw} fill={fill} />
        <text textAnchor="middle" dy="3" fill="#5a8a5a" fontSize="9">{data?.page_number ?? ''}</text></g>)
    case 'chunk':
      return (<g><DiamondShape r={r} stroke={stroke} sw={sw} fill={fill} />
        <text textAnchor="middle" dy="3" fill={stroke} fontSize="7">◆</text></g>)
    default:
      return (<g><DiamondShape r={r} stroke={stroke} sw={sw} fill={fill} />
        <text textAnchor="middle" dy="3" fill="#5a8a5a" fontSize="6">{elementIcon(data?.element_type)}</text></g>)
  }
}

/* ── Explorer sidebar row ── */
function ExplorerRow({ label, icon, depth, isExpanded, isActive, childCount, onToggle, onSelect }) {
  return (
    <button
      onClick={onSelect}
      className={`w-full text-left flex items-center gap-1 py-0.5 px-1.5 text-[10px] transition-colors ${
        isActive ? 'text-[#00ff41]' : 'text-[#5a8a5a] hover:text-[#8ab88a]'
      }`}
      style={{ paddingLeft: `${depth * 10 + 6}px` }}
    >
      {onToggle ? (
        <span
          className="w-3 text-center shrink-0 cursor-pointer hover:text-[#00ff41]"
          onClick={(e) => { e.stopPropagation(); onToggle() }}
        >
          {isExpanded ? '▾' : '▸'}
        </span>
      ) : (
        <span className="w-3 text-center shrink-0 text-[#2a4a2a]">{icon}</span>
      )}
      <span className="truncate flex-1">{label}</span>
      {childCount > 0 && (
        <span className="text-[#2a4a2a] text-[9px] shrink-0 ml-auto">{childCount}</span>
      )}
    </button>
  )
}


export default function GraphView({
  headingTree, pages, chunks,
  byHeading, orphans, chunksByPage,
  elementsCache, loadingPages,
  selected, onSelect, onFetchElements,
  documentName,
}) {
  const containerRef = useRef(null)
  const [dims, setDims] = useState({ w: 800, h: 600 })
  const isLargeDoc = pages.length >= LARGE_DOC_THRESHOLD
  const [graphExpanded, setGraphExpanded] = useState(() =>
    new Set(isLargeDoc ? [] : ['root'])
  )
  const [hoveredId, setHoveredId] = useState(null)
  const [viewBox, setViewBox] = useState(null)
  const [isPanning, setIsPanning] = useState(false)
  const panStart = useRef(null)
  const dragId = useRef(null)

  // If doc turns out to be large after pages load, collapse root
  const prevPageCount = useRef(pages.length)
  useEffect(() => {
    if (prevPageCount.current < LARGE_DOC_THRESHOLD && pages.length >= LARGE_DOC_THRESHOLD) {
      setGraphExpanded(new Set())
    }
    prevPageCount.current = pages.length
  }, [pages.length])

  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const ro = new ResizeObserver(([entry]) => {
      setDims({ w: entry.contentRect.width, h: entry.contentRect.height })
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  const effectiveViewBox = viewBox || { x: 0, y: 0, w: dims.w, h: dims.h }

  // Build the focused path — for each parent, which child (if any) is expanded
  const focusedChildren = useMemo(() => {
    const map = new Map() // parentId → expanded child id (or null)
    // Root's children: headings + orphan pages
    for (const h of headingTree) {
      if (graphExpanded.has(h.id)) { map.set('root', h.id); break }
    }
    if (!map.has('root')) {
      for (const p of orphans) {
        const pid = `page-${p.page_number}`
        if (graphExpanded.has(pid)) { map.set('root', pid); break }
      }
    }
    // Heading children
    function walkFocus(heading) {
      if (!graphExpanded.has(heading.id)) return
      const directPages = byHeading[heading.id] || []
      for (const sub of heading.subHeadings) {
        if (graphExpanded.has(sub.id)) { map.set(heading.id, sub.id); walkFocus(sub); return }
      }
      for (const p of directPages) {
        const pid = `page-${p.page_number}`
        if (graphExpanded.has(pid)) { map.set(heading.id, pid); return }
      }
    }
    for (const h of headingTree) walkFocus(h)
    return map
  }, [graphExpanded, headingTree, orphans, byHeading])

  // Build flat nodes + links — with progressive focus (hide siblings when one is expanded)
  const { nodes, links } = useMemo(() => {
    const ns = []
    const ls = []
    const exp = graphExpanded

    // Graph inactive — return empty
    if (exp.size === 0) return { nodes: ns, links: ls }

    ns.push({
      id: 'root', type: 'document', label: documentName || 'Document',
      parentId: null, depth: 0, childCount: headingTree.length + orphans.length,
      expanded: exp.has('root'), data: null,
    })

    if (!exp.has('root')) return { nodes: ns, links: ls }

    function walkHeading(heading, parentId, depth) {
      const nid = heading.id
      const directPages = byHeading[heading.id] || []
      ns.push({
        id: nid, type: 'heading', label: heading.text,
        parentId, depth, childCount: heading.subHeadings.length + directPages.length,
        expanded: exp.has(nid), data: heading,
      })
      ls.push({ source: parentId, target: nid })

      if (!exp.has(nid)) return

      // Progressive focus: if any sub-heading is expanded, only show that one
      const focusedChild = focusedChildren.get(nid)
      const expandedSub = heading.subHeadings.find(s => s.id === focusedChild)
      const subsToShow = expandedSub ? [expandedSub] : heading.subHeadings

      // Same for pages: if one is expanded, focus on it
      const sortedPages = directPages.sort((a, b) => a.page_number - b.page_number)
      const expandedPage = sortedPages.find(p => `page-${p.page_number}` === focusedChild)
      const pagesToShow = expandedPage ? [expandedPage] : sortedPages

      for (const sub of subsToShow) walkHeading(sub, nid, depth + 1)
      for (const page of pagesToShow) addPage(page, nid, depth + 1)
    }

    function addPage(page, parentId, depth) {
      const nid = `page-${page.page_number}`
      const els = elementsCache[page.page_number]
      const pChunks = chunksByPage[page.page_number] || []
      const bodyEls = els?.filter(e => e.content_layer === 'body' && (e.full_text || e.text_preview || e.element_type === 'picture')) || []

      ns.push({
        id: nid, type: 'page', label: `Page ${page.page_number}`,
        parentId, depth, childCount: bodyEls.length + pChunks.length,
        expanded: exp.has(nid), data: page,
      })
      ls.push({ source: parentId, target: nid })

      if (!exp.has(nid)) return

      bodyEls
        .sort((a, b) => a.reading_order - b.reading_order)
        .slice(0, MAX_ELEMENTS_PER_PAGE)
        .forEach(el => {
          const eid = `el-${el.element_id}`
          ns.push({
            id: eid, type: 'element',
            label: el.element_type === 'picture' ? 'Image' : truncate(el.full_text || el.text_preview, 18),
            parentId: nid, depth: depth + 1, childCount: 0,
            expanded: false, data: el,
          })
          ls.push({ source: nid, target: eid })
        })

      for (const ch of pChunks) {
        const cid = `ch-${ch.chunk_id}`
        if (ns.some(n => n.id === cid)) continue
        ns.push({
          id: cid, type: 'chunk', label: truncate(ch.content, 18),
          parentId: nid, depth: depth + 1, childCount: 0,
          expanded: false, data: ch,
        })
        ls.push({ source: nid, target: cid })
      }
    }

    // Root children — progressive focus applies here too
    const focusedRoot = focusedChildren.get('root')

    const sortedOrphans = orphans.sort((a, b) => a.page_number - b.page_number)
    const expandedOrphan = sortedOrphans.find(p => `page-${p.page_number}` === focusedRoot)
    const orphansToShow = expandedOrphan ? [expandedOrphan] : (focusedRoot && !expandedOrphan ? [] : sortedOrphans)

    const expandedHeading = headingTree.find(h => h.id === focusedRoot)
    const headingsToShow = expandedHeading ? [expandedHeading] : (focusedRoot && !expandedHeading ? [] : headingTree)

    for (const page of orphansToShow) addPage(page, 'root', 1)
    for (const h of headingsToShow) walkHeading(h, 'root', 1)

    if (headingTree.length === 0 && orphans.length === 0) {
      const allPages = [...pages].sort((a, b) => a.page_number - b.page_number)
      const focusedPage = allPages.find(p => `page-${p.page_number}` === focusedRoot)
      const pagesToShow = focusedPage ? [focusedPage] : allPages
      for (const page of pagesToShow) addPage(page, 'root', 1)
    }

    return { nodes: ns, links: ls }
  }, [graphExpanded, focusedChildren, headingTree, pages, orphans, byHeading, chunksByPage, elementsCache, chunks, documentName])

  const graphActive = graphExpanded.size > 0
  const { positions, reheat, dragStart, dragMove, dragEnd } = useForceLayout({
    nodes, links, width: dims.w, height: dims.h, enabled: graphActive,
  })

  // Breadcrumb: the focused drill-down path
  const breadcrumb = useMemo(() => {
    const path = [{ id: 'root', label: documentName || 'Document', type: 'document' }]
    let current = 'root'
    while (focusedChildren.has(current)) {
      const childId = focusedChildren.get(current)
      const node = nodes.find(n => n.id === childId)
      if (!node) break
      path.push({ id: node.id, label: node.label, type: node.type })
      current = childId
    }
    return path
  }, [focusedChildren, nodes, documentName])

  // Labels visible for: root, headings, selected, hovered
  const visibleLabels = useMemo(() => {
    const set = new Set(['root'])
    if (selected) set.add(selected.id)
    if (hoveredId) set.add(hoveredId)
    for (const node of nodes) {
      if (node.type === 'heading' || node.type === 'document') set.add(node.id)
    }
    return set
  }, [selected, hoveredId, nodes])

  // Find the ancestor path from root to a given node ID
  const findPath = useCallback((targetId) => {
    if (targetId === 'root') return ['root']

    // Check if target is a heading — walk the heading tree
    function walkHeadings(headings, path) {
      for (const h of headings) {
        if (h.id === targetId) return [...path, h.id]
        const found = walkHeadings(h.subHeadings, [...path, h.id])
        if (found) return found
      }
      return null
    }
    const headingPath = walkHeadings(headingTree, ['root'])
    if (headingPath) return headingPath

    // Check if target is a page — find its parent heading
    const pageMatch = targetId.match(/^page-(\d+)$/)
    if (pageMatch) {
      const pageNum = parseInt(pageMatch[1])
      for (const [hid, hpages] of Object.entries(byHeading)) {
        if (hpages.some(p => p.page_number === pageNum)) {
          // Find the heading path first, then append the page
          function walkForHeading(headings, path) {
            for (const h of headings) {
              if (h.id === hid) return [...path, h.id]
              const found = walkForHeading(h.subHeadings, [...path, h.id])
              if (found) return found
            }
            return null
          }
          const hp = walkForHeading(headingTree, ['root'])
          if (hp) return [...hp, targetId]
        }
      }
      // Orphan page — direct child of root
      if (orphans.some(p => `page-${p.page_number}` === targetId)) {
        return ['root', targetId]
      }
      // Flat pages (no headings)
      return ['root', targetId]
    }

    return ['root']
  }, [headingTree, byHeading, orphans])

  // Navigate to a node: expand the full ancestor path and select it
  const navigateTo = useCallback((targetId, selectPayload, pageData) => {
    const path = findPath(targetId)

    setGraphExpanded(prev => {
      const next = new Set(path)
      return next
    })

    // Trigger lazy load for any pages in the path
    if (pageData?.page_id) {
      onFetchElements(pageData.page_id, pageData.page_number)
    }

    if (selectPayload) onSelect(selectPayload)
    setViewBox(null)
    reheat()
  }, [findPath, onFetchElements, onSelect, reheat])

  const toggleExpand = useCallback((nodeId, nodeOrData) => {
    setGraphExpanded(prev => {
      const next = new Set(prev)
      if (next.has(nodeId)) {
        // Collapse: also collapse all descendants
        const toRemove = [nodeId]
        while (toRemove.length) {
          const rid = toRemove.pop()
          next.delete(rid)
          for (const n of nodes) {
            if (n.parentId === rid && next.has(n.id)) toRemove.push(n.id)
          }
        }
      } else {
        next.add(nodeId)
        // Trigger lazy loading for pages
        const data = nodeOrData?.data || nodeOrData
        if (data?.page_id) {
          onFetchElements(data.page_id, data.page_number)
        }
      }
      return next
    })
    setViewBox(null) // Reset view to re-center on new layout
    reheat()
  }, [onFetchElements, reheat, nodes])

  const handleNodeClick = useCallback((node) => {
    if (node.type === 'document') return
    if (node.type === 'heading') {
      onSelect({ type: 'heading', id: node.id, data: node.data })
    } else if (node.type === 'page') {
      onSelect({ type: 'page', id: node.id, pageId: node.data.page_id, pageNumber: node.data.page_number, data: node.data })
    } else if (node.type === 'element') {
      const pageNode = nodes.find(n => n.id === node.parentId)
      onSelect({ type: 'element', id: node.id, data: node.data, pageNumber: pageNode?.data?.page_number })
    } else if (node.type === 'chunk') {
      onSelect({ type: 'chunk', id: `ch-${node.data.chunk_id}`, chunkId: node.data.chunk_id, data: node.data })
    }
  }, [onSelect, nodes])

  const handleNodeDblClick = useCallback((e, node) => {
    e.preventDefault()
    if (node.childCount > 0 || node.type === 'page' || node.type === 'heading' || node.type === 'document') {
      toggleExpand(node.id, node)
    }
  }, [toggleExpand])

  const svgPoint = useCallback((clientX, clientY) => {
    const svg = containerRef.current?.querySelector('svg')
    if (!svg) return { x: clientX, y: clientY }
    const pt = svg.createSVGPoint()
    pt.x = clientX; pt.y = clientY
    return pt.matrixTransform(svg.getScreenCTM().inverse())
  }, [])

  const handleBgPointerDown = useCallback((e) => {
    if (e.target.tagName === 'svg' || e.target.dataset.bg) {
      setIsPanning(true)
      panStart.current = { x: e.clientX, y: e.clientY, vb: { ...effectiveViewBox } }
      e.currentTarget.setPointerCapture(e.pointerId)
    }
  }, [effectiveViewBox])

  const handlePointerMove = useCallback((e) => {
    if (isPanning && panStart.current) {
      const dx = e.clientX - panStart.current.x
      const dy = e.clientY - panStart.current.y
      const scale = effectiveViewBox.w / dims.w
      setViewBox({ ...panStart.current.vb, x: panStart.current.vb.x - dx * scale, y: panStart.current.vb.y - dy * scale })
    } else if (dragId.current) {
      const { x, y } = svgPoint(e.clientX, e.clientY)
      dragMove(dragId.current, x, y)
    }
  }, [isPanning, effectiveViewBox.w, dims.w, svgPoint, dragMove])

  const handlePointerUp = useCallback(() => {
    if (isPanning) { setIsPanning(false); panStart.current = null }
    if (dragId.current) { dragEnd(dragId.current); dragId.current = null }
  }, [isPanning, dragEnd])

  const handleWheel = useCallback((e) => {
    e.preventDefault()
    const factor = e.deltaY > 0 ? 1.08 : 0.93
    const vb = effectiveViewBox
    const newW = vb.w * factor; const newH = vb.h * factor
    const rect = containerRef.current.getBoundingClientRect()
    const mx = (e.clientX - rect.left) / rect.width
    const my = (e.clientY - rect.top) / rect.height
    setViewBox({ x: vb.x - (newW - vb.w) * mx, y: vb.y - (newH - vb.h) * my, w: newW, h: newH })
  }, [effectiveViewBox])

  const handleNodePointerDown = useCallback((e, node) => {
    e.stopPropagation()
    dragId.current = node.id
    dragStart(node.id)
    e.currentTarget.setPointerCapture(e.pointerId)
  }, [dragStart])

  function linkStroke(source) {
    const sNode = nodes.find(n => n.id === source)
    const depth = sNode?.depth ?? 0
    if (depth <= 0) return '#1e4a1e'
    if (depth <= 1) return '#163816'
    return '#122a12'
  }

  /* ── Explorer sidebar: render heading tree ── */
  function renderExplorerHeading(heading, depth) {
    const nid = heading.id
    const isExp = graphExpanded.has(nid)
    const isActive = selected?.id === nid
    const directPages = byHeading[heading.id] || []
    const pageCount = directPages.length
    const hasChildren = heading.subHeadings.length > 0 || pageCount > 0

    return (
      <div key={nid}>
        <ExplorerRow
          label={heading.text}
          depth={depth}
          isExpanded={isExp}
          isActive={isActive}
          childCount={pageCount || null}
          onToggle={hasChildren ? () => {
            if (isExp) {
              toggleExpand(nid, { data: heading })
            } else {
              navigateTo(nid, { type: 'heading', id: nid, data: heading })
            }
          } : null}
          onSelect={() => {
            navigateTo(nid, { type: 'heading', id: nid, data: heading })
          }}
        />
        {isExp && (
          <>
            {heading.subHeadings.map(sub => renderExplorerHeading(sub, depth + 1))}
            {directPages
              .sort((a, b) => a.page_number - b.page_number)
              .map(page => {
                const pid = `page-${page.page_number}`
                const pExp = graphExpanded.has(pid)
                const pChunks = chunksByPage[page.page_number] || []
                return (
                  <ExplorerRow
                    key={pid}
                    label={`Page ${page.page_number}`}
                    icon="▫"
                    depth={depth + 1}
                    isExpanded={pExp}
                    isActive={selected?.id === pid}
                    childCount={pChunks.length ? `${pChunks.length}ch` : null}
                    onToggle={() => {
                      if (graphExpanded.has(pid)) {
                        toggleExpand(pid, { data: page })
                      } else {
                        navigateTo(pid, null, { page_id: page.page_id, page_number: page.page_number })
                      }
                    }}
                    onSelect={() => {
                      navigateTo(pid,
                        { type: 'page', id: pid, pageId: page.page_id, pageNumber: page.page_number, data: page },
                        { page_id: page.page_id, page_number: page.page_number },
                      )
                    }}
                  />
                )
              })}
          </>
        )}
      </div>
    )
  }

  return (
    <div
      ref={containerRef}
      className="w-full h-full relative overflow-hidden"
      style={{ cursor: isPanning ? 'grabbing' : 'grab' }}
    >
      {/* ── Explorer sidebar ── */}
      <div className="absolute top-0 left-0 bottom-0 w-[180px] z-10 bg-[#060d06]/90 backdrop-blur-sm border-r border-[#0d2b0d] flex flex-col">
        <div className="px-2 py-1.5 border-b border-[#0d2b0d]">
          <p className="text-[9px] font-medium text-[#3d6b3d] uppercase tracking-wider">Explorer</p>
        </div>
        <ScrollArea className="flex-1">
          <div className="py-0.5">
            {headingTree.length > 0 ? (
              headingTree.map(h => renderExplorerHeading(h, 0))
            ) : (
              pages
                .sort((a, b) => a.page_number - b.page_number)
                .map(page => (
                  <ExplorerRow
                    key={`page-${page.page_number}`}
                    label={`Page ${page.page_number}`}
                    icon="▫"
                    depth={0}
                    isActive={selected?.id === `page-${page.page_number}`}
                    onSelect={() => navigateTo(
                      `page-${page.page_number}`,
                      { type: 'page', id: `page-${page.page_number}`, pageId: page.page_id, pageNumber: page.page_number, data: page },
                      { page_id: page.page_id, page_number: page.page_number },
                    )}
                  />
                ))
            )}
          </div>
        </ScrollArea>
      </div>

      {/* ── Large doc prompt ── */}
      {!graphActive && (
        <div className="absolute inset-0 left-[180px] flex items-center justify-center z-5">
          <div className="text-center space-y-3 max-w-[280px]">
            <div className="text-[#1e4a1e] text-4xl">§</div>
            <p className="text-sm text-[#5a8a5a]">
              Large document ({pages.length} pages)
            </p>
            <p className="text-xs text-[#3d6b3d] leading-relaxed">
              Select a chapter from the explorer to start exploring the graph.
            </p>
          </div>
        </div>
      )}

      {/* ── Breadcrumb ── */}
      {breadcrumb.length > 1 && (
        <div className="absolute top-2 left-[192px] z-10 flex items-center gap-1 text-[10px] select-none">
          {breadcrumb.map((crumb, i) => (
            <span key={crumb.id} className="flex items-center gap-1">
              {i > 0 && <span className="text-[#2a4a2a]">›</span>}
              <button
                className={`px-1.5 py-0.5 rounded transition-colors ${
                  i === breadcrumb.length - 1
                    ? 'text-[#00ff41] bg-[#00ff41]/10'
                    : 'text-[#5a8a5a] hover:text-[#8ab88a]'
                }`}
                onClick={() => {
                  // Collapse everything after this crumb
                  setGraphExpanded(prev => {
                    const next = new Set(prev)
                    // Remove all expansions that came after this level
                    for (let j = i + 1; j < breadcrumb.length; j++) {
                      next.delete(breadcrumb[j].id)
                    }
                    return next
                  })
                  setViewBox(null)
                  reheat()
                }}
              >
                {truncate(crumb.label, 16)}
              </button>
            </span>
          ))}
        </div>
      )}

      {/* ── SVG Graph ── */}
      <svg
        width="100%"
        height="100%"
        viewBox={`${effectiveViewBox.x} ${effectiveViewBox.y} ${effectiveViewBox.w} ${effectiveViewBox.h}`}
        onPointerDown={handleBgPointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onWheel={handleWheel}
        className="select-none"
        style={{ paddingLeft: '180px' }}
      >
        <defs>
          <filter id="node-glow">
            <feGaussianBlur stdDeviation="3" result="blur" />
            <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
          </filter>
          <filter id="node-glow-cyan">
            <feGaussianBlur stdDeviation="2.5" result="blur" />
            <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
          </filter>
        </defs>

        <rect data-bg="true"
          x={effectiveViewBox.x} y={effectiveViewBox.y}
          width={effectiveViewBox.w} height={effectiveViewBox.h}
          fill="transparent"
        />

        {/* Links */}
        <g>
          {links.map(l => {
            const sp = positions.get(l.source)
            const tp = positions.get(l.target)
            if (!sp || !tp) return null
            return (
              <line key={`${l.source}-${l.target}`}
                x1={sp.x} y1={sp.y} x2={tp.x} y2={tp.y}
                stroke={linkStroke(l.source)} strokeWidth={1}
                className="graph-link-draw"
              />
            )
          })}
        </g>

        {/* Nodes */}
        <g>
          {nodes.map(node => {
            const pos = positions.get(node.id)
            if (!pos) return null
            const isSelected = selected?.id === node.id
            const isHovered = hoveredId === node.id
            const cfg = NODE_CONFIG[node.type] || NODE_CONFIG.element
            const canExpand = node.childCount > 0 || node.type === 'page' || node.type === 'heading' || node.type === 'document'

            return (
              <g key={node.id}
                transform={`translate(${pos.x}, ${pos.y})`}
                style={{ cursor: 'pointer' }}
                onPointerDown={(e) => handleNodePointerDown(e, node)}
                onPointerEnter={() => setHoveredId(node.id)}
                onPointerLeave={() => setHoveredId(prev => prev === node.id ? null : prev)}
                onClick={() => handleNodeClick(node)}
                onDoubleClick={(e) => handleNodeDblClick(e, node)}
              >
                <g className="graph-node-appear"
                  filter={node.type === 'chunk' ? 'url(#node-glow-cyan)' : 'url(#node-glow)'}
                >
                  {isSelected && (
                    <circle r={cfg.size + 6} fill="none"
                      stroke={node.type === 'chunk' ? '#00e5ff' : '#00ff41'}
                      strokeWidth={1.5} opacity={0.5}
                      style={{ animation: 'graph-node-pulse 1.5s ease-in-out infinite' }}
                    />
                  )}
                  {isHovered && !isSelected && (
                    <circle r={cfg.size + 4} fill="none" stroke="#00ff41" strokeWidth={0.8} opacity={0.3} />
                  )}
                  <NodeShape type={node.type} data={node.data} />
                  {canExpand && (
                    <g transform={`translate(${cfg.size + 3}, ${-cfg.size + 1})`}
                      onClick={(e) => { e.stopPropagation(); toggleExpand(node.id, node) }}
                    >
                      <circle r={7} fill="#0a0f0a" stroke="#3d6b3d" strokeWidth={0.8} />
                      <text textAnchor="middle" dy="3.5" fill="#00ff41" fontSize="10" fontWeight="bold">
                        {node.expanded ? '−' : '+'}
                      </text>
                    </g>
                  )}
                </g>
              </g>
            )
          })}
        </g>

        {/* Labels */}
        <g>
          {nodes.map(node => {
            if (!visibleLabels.has(node.id)) return null
            const pos = positions.get(node.id)
            if (!pos) return null
            const cfg = NODE_CONFIG[node.type] || NODE_CONFIG.element
            const yOff = node.type === 'page' ? cfg.size * 1.3 + 10 : cfg.size + 10
            return (
              <text key={`lbl-${node.id}`}
                x={pos.x} y={pos.y + yOff} textAnchor="middle"
                fill={node.id === hoveredId || selected?.id === node.id ? '#c8e6c8' : '#5a8a5a'}
                fontSize={node.type === 'document' ? 11 : 9}
                fontFamily="'Share Tech Mono', monospace"
                style={{ pointerEvents: 'none' }}
              >
                {truncate(node.label, 28)}
              </text>
            )
          })}

          {/* Hover tooltip */}
          {hoveredId && !visibleLabels.has(hoveredId) && (() => {
            const node = nodes.find(n => n.id === hoveredId)
            const pos = node && positions.get(node.id)
            if (!node || !pos) return null
            const cfg = NODE_CONFIG[node.type] || NODE_CONFIG.element
            const yOff = node.type === 'page' ? cfg.size * 1.3 + 10 : cfg.size + 10
            const label = truncate(node.label, 32)
            const labelW = label.length * 5.5 + 12
            return (
              <g>
                <rect x={pos.x - labelW / 2} y={pos.y + yOff - 10}
                  width={labelW} height={16} rx={3}
                  fill="#0a0f0a" fillOpacity={0.9} stroke="#1a3a1a" strokeWidth={0.5}
                />
                <text x={pos.x} y={pos.y + yOff + 1} textAnchor="middle"
                  fill="#c8e6c8" fontSize={9} fontFamily="'Share Tech Mono', monospace"
                  style={{ pointerEvents: 'none' }}
                >{label}</text>
              </g>
            )
          })()}
        </g>
      </svg>

      {/* Node count */}
      <div className="absolute bottom-3 left-[192px] text-[10px] text-[#3d6b3d] select-none">
        {nodes.length} nodes · {links.length} links
      </div>

      {viewBox && (
        <button onClick={() => setViewBox(null)}
          className="absolute bottom-3 right-3 text-[10px] text-[#3d6b3d] hover:text-[#00ff41] transition-colors px-2 py-1 border border-[#1a3a1a] rounded bg-[#0a0f0a]/80"
        >Reset view</button>
      )}
    </div>
  )
}

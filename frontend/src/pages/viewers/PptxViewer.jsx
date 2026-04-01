import { useState, useEffect, useCallback, useRef } from 'react'
import {
  getDocumentPages,
  getChunks,
  getChunk,
  getChunkTables,
  getChunkImages,
  getDocumentImages,
  getPageElements,
  getImageUrl,
} from '../../api/client'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import TreeRow from './shared/TreeRow'
import ElementRenderer from './shared/ElementRenderer'
import ChunkDetail from './shared/ChunkDetail'

function truncate(str, len = 50) {
  if (!str) return ''
  return str.length > len ? str.slice(0, len) + '…' : str
}

export default function PptxViewer({ documentId }) {
  const [pages, setPages] = useState([])
  const [chunks, setChunks] = useState([])
  const [docImages, setDocImages] = useState([])
  const [loading, setLoading] = useState(true)

  const [selected, setSelected] = useState(null)

  const [elementsCache, setElementsCache] = useState({})
  const elementsCacheRef = useRef({})
  const loadingPagesRef = useRef(new Set())
  const [loadingPages, setLoadingPages] = useState(new Set())

  const [chunkDetail, setChunkDetail] = useState(null)
  const [chunkTables, setChunkTables] = useState([])
  const [chunkImages, setChunkImages] = useState([])
  const [detailLoading, setDetailLoading] = useState(false)

  useEffect(() => {
    let cancelled = false
    const fetchAll = async () => {
      setLoading(true)
      try {
        const [p, c, imgs] = await Promise.all([
          getDocumentPages(documentId),
          getChunks(documentId),
          getDocumentImages(documentId),
        ])
        if (cancelled) return
        const pArr = p?.pages ?? p
        setPages(Array.isArray(pArr) ? pArr : [])
        const cArr = c?.chunks ?? c
        setChunks(Array.isArray(cArr) ? cArr : [])
        const iArr = imgs?.images ?? imgs
        setDocImages(Array.isArray(iArr) ? iArr : [])
      } catch (e) {
        console.error('Failed to load document:', e)
      }
      if (!cancelled) setLoading(false)
    }
    fetchAll()
    return () => { cancelled = true }
  }, [documentId])

  // Map images by page number for inline rendering
  const imagesByPage = {}
  for (const img of docImages) {
    ;(imagesByPage[img.page_number] ??= []).push(img)
  }

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
      console.error(`Failed to load elements for slide ${pageNumber}:`, e)
      elementsCacheRef.current[pageNumber] = []
      setElementsCache({ ...elementsCacheRef.current })
    }
    loadingPagesRef.current.delete(pageNumber)
    setLoadingPages(new Set(loadingPagesRef.current))
  }, [])

  const selectSlide = useCallback((page) => {
    setSelected({ type: 'slide', id: `slide-${page.page_number}`, data: page, pageNumber: page.page_number })
    setChunkDetail(null)
    setChunkTables([])
    setChunkImages([])
    fetchElements(page.page_id, page.page_number)
  }, [fetchElements])

  const selectChunk = useCallback(async (ch) => {
    setSelected({ type: 'chunk', id: `ch-${ch.chunk_id}`, chunkId: ch.chunk_id, data: ch })
    setDetailLoading(true)
    try {
      const [detail, tables, images] = await Promise.all([
        getChunk(ch.chunk_id),
        getChunkTables(ch.chunk_id),
        getChunkImages(ch.chunk_id),
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
  }, [])

  const renderDetail = () => {
    if (!selected) {
      return (
        <div className="h-full flex items-center justify-center">
          <p className="text-sm text-warm-500">Select a slide to view its content</p>
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

    // Slide detail
    const page = selected.data
    const els = elementsCache[selected.pageNumber]
    const isLoading = loadingPages.has(selected.pageNumber)
    const slideImages = imagesByPage[selected.pageNumber] || []

    return (
      <div className="p-5 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-warm-900">Slide {page.page_number}</h2>
          <div className="flex gap-2">
            {els && (
              <Badge variant="outline" className="text-warm-600 border-warm-200 text-xs">
                {els.filter(e => e.content_layer === 'body').length} elements
              </Badge>
            )}
            {slideImages.length > 0 && (
              <Badge variant="outline" className="text-[#b388ff] border-[#b388ff]/30 text-xs">
                {slideImages.length} images
              </Badge>
            )}
          </div>
        </div>

        {isLoading && <p className="text-sm text-warm-500">Loading slide content…</p>}

        {els && (
          <div className="p-5 bg-warm-100 rounded-xl border border-warm-200">
            {els
              .filter(e => e.content_layer === 'body')
              .sort((a, b) => a.reading_order - b.reading_order)
              .map((el, i) => {
                // For picture elements, try to match an image from this slide
                let imageUrl = null
                if (el.element_type === 'picture' && slideImages.length > 0) {
                  // Use the first unmatched image for this slide
                  const img = slideImages[0]
                  if (img) imageUrl = getImageUrl(img.image_id)
                }
                return <ElementRenderer key={el.element_id || i} element={el} imageUrl={imageUrl} />
              })}
            {els.filter(e => e.content_layer === 'body').length === 0 && (
              <p className="text-sm text-warm-500">No body elements on this slide</p>
            )}
          </div>
        )}

        {/* Show all images for this slide */}
        {slideImages.length > 0 && (
          <div className="space-y-2">
            <p className="text-xs font-medium text-warm-500 uppercase tracking-wider">
              Slide Images ({slideImages.length})
            </p>
            {slideImages.map(img => (
              <div key={img.image_id} className="space-y-1">
                <img
                  src={getImageUrl(img.image_id)}
                  alt={img.caption || `Image ${img.image_id}`}
                  className="max-w-full rounded-lg border border-warm-200"
                />
                {img.caption && <p className="text-xs text-warm-600 italic">{img.caption}</p>}
                <div className="flex gap-2">
                  <Badge variant="outline" className="text-[#b388ff] border-[#b388ff]/30 text-xs">
                    {img.width} × {img.height}
                  </Badge>
                  {img.file_size && (
                    <Badge variant="outline" className="text-warm-500 border-warm-200 text-xs">
                      {(img.file_size / 1024).toFixed(1)} KB
                    </Badge>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    )
  }

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <p className="text-warm-500">Loading presentation…</p>
      </div>
    )
  }

  return (
    <div className="flex-1 grid grid-cols-[320px_1fr] min-h-0">
      <aside className="border-r border-warm-200 flex flex-col min-h-0">
        <div className="px-4 py-2.5 border-b border-warm-200">
          <h2 className="text-xs font-medium text-warm-600 uppercase tracking-wider">Slides</h2>
        </div>
        <ScrollArea className="flex-1">
          <div className="py-1">
            {pages
              .sort((a, b) => a.page_number - b.page_number)
              .map(page => {
                const slideImages = imagesByPage[page.page_number] || []
                const parts = []
                if (page.element_count) parts.push(`${page.element_count} el`)
                if (slideImages.length) parts.push(`${slideImages.length} img`)

                return (
                  <TreeRow
                    key={page.page_number}
                    depth={0}
                    icon="▪"
                    label={`Slide ${page.page_number}`}
                    meta={parts.join(' · ') || null}
                    selected={selected?.id === `slide-${page.page_number}`}
                    onClick={() => selectSlide(page)}
                  />
                )
              })}

            {/* Document-level chunks */}
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
              <p className="text-xs text-warm-500 px-4 py-2">No slides found</p>
            )}
          </div>
        </ScrollArea>
      </aside>

      <main className="flex flex-col min-h-0">
        <div className="px-4 py-2.5 border-b border-warm-200">
          <h2 className="text-xs font-medium text-warm-600 uppercase tracking-wider">
            {selected
              ? selected.type === 'slide' ? 'Slide View'
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

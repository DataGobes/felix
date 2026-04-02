import { useState } from 'react'
import { Badge } from '@/components/ui/badge'
import { getImageUrl } from '../../../api/client'
import TableRenderer from './TableRenderer'

export default function ChunkDetail({ chunk, tables = [], images = [], loading }) {
  const [contentExpanded, setContentExpanded] = useState(false)
  if (loading) {
    return <div className="p-5"><p className="text-sm text-warm-500">Loading chunk…</p></div>
  }

  if (!chunk) return null

  return (
    <div className="p-5 space-y-4 overflow-hidden">
      <div>
        <p className="text-xs font-medium text-warm-500 uppercase tracking-wider mb-1">Chunk</p>
        <div className="flex flex-wrap gap-2">
          <Badge variant="outline" className="text-ember border-ember/30 text-xs">
            chunk {chunk.chunk_index}
          </Badge>
          <Badge variant="outline" className="text-warm-600 border-warm-600/30 text-xs">
            {chunk.token_count} tokens
          </Badge>
          {chunk.char_count && (
            <Badge variant="outline" className="text-warm-500 border-warm-200 text-xs">
              {chunk.char_count} chars
            </Badge>
          )}
          {chunk.page_number && (
            <Badge variant="outline" className="text-warm-500 border-warm-200 text-xs">
              page {chunk.page_number}
            </Badge>
          )}
        </div>
      </div>

      {chunk.headings?.length > 0 && (
        <div className="space-y-1">
          <p className="text-xs font-medium text-warm-500 uppercase tracking-wider">Headings</p>
          <p className="text-sm text-ember">{chunk.headings.join(' › ')}</p>
        </div>
      )}

      <div className="space-y-1">
        <p className="text-xs font-medium text-warm-500 uppercase tracking-wider">Content</p>
        <div className="relative">
          <div className={`p-4 bg-warm-100 rounded-lg border border-warm-200 text-sm text-warm-900 whitespace-pre-wrap leading-relaxed break-words overflow-hidden ${
            contentExpanded ? '' : 'max-h-40'
          }`}>
            {chunk.content}
          </div>
          {chunk.content?.length > 300 && (
            <button
              onClick={() => setContentExpanded(v => !v)}
              className="mt-1 text-xs text-ember hover:text-ember/80 font-medium transition-colors"
            >
              {contentExpanded ? '▲ Collapse' : '▼ Show full content'}
            </button>
          )}
        </div>
      </div>

      {images.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs font-medium text-warm-500 uppercase tracking-wider">
            Images ({images.length})
          </p>
          {images.map(img => (
            <div key={img.image_id} className="space-y-2">
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

      {tables.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs font-medium text-warm-500 uppercase tracking-wider">
            Tables ({tables.length})
          </p>
          {tables.map((table, i) => (
            <TableRenderer key={i} table={table} />
          ))}
        </div>
      )}
    </div>
  )
}

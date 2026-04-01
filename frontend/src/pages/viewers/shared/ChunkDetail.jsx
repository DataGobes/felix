import { Badge } from '@/components/ui/badge'
import { getImageUrl } from '../../../api/client'
import TableRenderer from './TableRenderer'

export default function ChunkDetail({ chunk, tables = [], images = [], loading }) {
  if (loading) {
    return <div className="p-5"><p className="text-sm text-[#3d6b3d]">Loading chunk…</p></div>
  }

  if (!chunk) return null

  return (
    <div className="p-5 space-y-4">
      <div>
        <p className="text-xs font-medium text-[#3d6b3d] uppercase tracking-wider mb-1">Chunk</p>
        <div className="flex flex-wrap gap-2">
          <Badge variant="outline" className="text-[#00ff41] border-[#00ff41]/30 text-xs">
            chunk {chunk.chunk_index}
          </Badge>
          <Badge variant="outline" className="text-[#00e5ff] border-[#00e5ff]/30 text-xs">
            {chunk.token_count} tokens
          </Badge>
          {chunk.char_count && (
            <Badge variant="outline" className="text-[#3d6b3d] border-[#1a3a1a] text-xs">
              {chunk.char_count} chars
            </Badge>
          )}
          {chunk.page_number && (
            <Badge variant="outline" className="text-[#3d6b3d] border-[#1a3a1a] text-xs">
              page {chunk.page_number}
            </Badge>
          )}
        </div>
      </div>

      {chunk.headings?.length > 0 && (
        <div className="space-y-1">
          <p className="text-xs font-medium text-[#3d6b3d] uppercase tracking-wider">Headings</p>
          <p className="text-sm text-[#00ff41]">{chunk.headings.join(' › ')}</p>
        </div>
      )}

      <div className="space-y-1">
        <p className="text-xs font-medium text-[#3d6b3d] uppercase tracking-wider">Content</p>
        <div className="p-4 bg-[#060d06] rounded-lg border border-[#0d2b0d] text-sm text-[#a8d8a8] whitespace-pre-wrap leading-relaxed">
          {chunk.content}
        </div>
      </div>

      {images.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs font-medium text-[#3d6b3d] uppercase tracking-wider">
            Images ({images.length})
          </p>
          {images.map(img => (
            <div key={img.image_id} className="space-y-2">
              <img
                src={getImageUrl(img.image_id)}
                alt={img.caption || `Image ${img.image_id}`}
                className="max-w-full rounded-lg border border-[#1a3a1a]"
              />
              {img.caption && <p className="text-xs text-[#5a8a5a] italic">{img.caption}</p>}
              <div className="flex gap-2">
                <Badge variant="outline" className="text-[#b388ff] border-[#b388ff]/30 text-xs">
                  {img.width} × {img.height}
                </Badge>
                {img.file_size && (
                  <Badge variant="outline" className="text-[#3d6b3d] border-[#1a3a1a] text-xs">
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
          <p className="text-xs font-medium text-[#3d6b3d] uppercase tracking-wider">
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

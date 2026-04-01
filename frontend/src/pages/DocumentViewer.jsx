import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { getDocument } from '../api/client'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'

import PdfViewer from './viewers/PdfViewer'
import PptxViewer from './viewers/PptxViewer'
import XlsxViewer from './viewers/XlsxViewer'
import TextViewer from './viewers/TextViewer'

const FORMAT_CONFIG = {
  pdf:  { label: 'PDF',  color: 'text-red-400 border-red-800',      Viewer: PdfViewer },
  pptx: { label: 'PPTX', color: 'text-orange-400 border-orange-800', Viewer: PptxViewer },
  ppt:  { label: 'PPT',  color: 'text-orange-400 border-orange-800', Viewer: PptxViewer },
  xlsx: { label: 'XLSX', color: 'text-green-400 border-green-800',   Viewer: XlsxViewer },
  xls:  { label: 'XLS',  color: 'text-green-400 border-green-800',   Viewer: XlsxViewer },
  txt:  { label: 'TXT',  color: 'text-blue-400 border-blue-800',     Viewer: TextViewer },
  md:   { label: 'MD',   color: 'text-blue-400 border-blue-800',     Viewer: TextViewer },
  csv:  { label: 'CSV',  color: 'text-cyan-400 border-cyan-800',     Viewer: TextViewer },
}

function getFormatFromDoc(doc) {
  const meta = typeof doc?.metadata === 'string' ? JSON.parse(doc.metadata) : doc?.metadata
  let ext = meta?.extension
  if (!ext && doc?.path) {
    const match = doc.path.match(/\.(\w+)$/)
    ext = match?.[1]
  }
  ext = ext?.toLowerCase()?.replace(/^\./, '')
  if (ext && FORMAT_CONFIG[ext]) return FORMAT_CONFIG[ext]
  return {
    label: ext ? ext.toUpperCase() : 'DOC',
    color: 'text-[#8ab88a] border-[#2a4a2a]',
    Viewer: TextViewer,
  }
}

function getFilename(doc) {
  if (!doc?.path) return 'Document'
  const parts = doc.path.split('/')
  return parts[parts.length - 1]
}

function DocumentViewer() {
  const { id } = useParams()
  const navigate = useNavigate()

  const [doc, setDoc] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false
    const fetchDoc = async () => {
      setLoading(true)
      setError(null)
      try {
        const data = await getDocument(id)
        if (!cancelled) setDoc(data?.document ?? data)
      } catch (e) {
        console.error('Failed to load document:', e)
        if (!cancelled) setError(e.message)
      }
      if (!cancelled) setLoading(false)
    }
    fetchDoc()
    return () => { cancelled = true }
  }, [id])

  if (loading) {
    return (
      <div className="h-screen bg-[#050505] text-[#c8e6c8] flex items-center justify-center">
        <p className="text-[#3d6b3d]">Loading document…</p>
      </div>
    )
  }

  if (error) {
    return (
      <div className="h-screen bg-[#050505] text-[#c8e6c8] flex flex-col items-center justify-center gap-4">
        <p className="text-red-400">Failed to load document: {error}</p>
        <Button
          onClick={() => navigate('/')}
          variant="ghost"
          size="sm"
          className="text-[#5a8a5a] hover:text-[#c8e6c8] hover:bg-[#00ff41]/10"
        >
          ← Back to Dashboard
        </Button>
      </div>
    )
  }

  const format = getFormatFromDoc(doc)
  const filename = getFilename(doc)
  const Viewer = format.Viewer

  return (
    <div className="h-screen bg-[#050505] text-[#c8e6c8] flex flex-col overflow-hidden">
      <header className="border-b border-[#0d2b0d] px-6 py-3 flex items-center gap-4 shrink-0">
        <Button
          onClick={() => navigate('/')}
          variant="ghost"
          size="sm"
          className="text-[#5a8a5a] hover:text-[#c8e6c8] hover:bg-[#00ff41]/10"
        >
          ← Back
        </Button>
        <h1 className="text-lg font-semibold tracking-tight truncate">{filename}</h1>
        <div className="ml-auto flex gap-2 shrink-0">
          <Badge variant="outline" className={`text-xs ${format.color}`}>
            {format.label}
          </Badge>
          {doc?.chunk_count != null && (
            <Badge variant="outline" className="text-[#5a8a5a] border-[#1a3a1a] text-xs">
              {doc.chunk_count} chunks
            </Badge>
          )}
        </div>
      </header>

      <Viewer documentId={id} />
    </div>
  )
}

export default DocumentViewer

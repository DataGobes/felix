import { useState, useEffect } from 'react'
import { getDocumentStructure } from '../api/client'

function ChunksViewer({ selectedDocumentId }) {
  const [structure, setStructure] = useState([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!selectedDocumentId) return
    const fetchStructure = async () => {
      setLoading(true)
      try {
        const data = await getDocumentStructure(selectedDocumentId)
        setStructure(data)
      } catch (error) {
        console.error('Failed to fetch structure:', error)
      }
      setLoading(false)
    }
    fetchStructure()
  }, [selectedDocumentId])

  return (
    <div className="bg-[#0a0f0a] rounded-xl shadow-lg shadow-black/20 overflow-hidden">
      <div className="px-6 pt-5 pb-4 flex items-center justify-between">
        <h2 className="text-xs font-medium text-[#3d6b3d] uppercase tracking-wider">Document Explorer</h2>
        {structure.length > 0 && (
          <span className="text-xs text-[#2a4a2a] tabular-nums">{structure.length} headings</span>
        )}
      </div>
      <div className="px-3 pb-3">
        {!selectedDocumentId && (
          <p className="text-sm text-[#3d6b3d] px-3 py-6 text-center">Select a document to explore its structure</p>
        )}
        {loading && (
          <p className="text-sm text-[#3d6b3d] px-3 py-6 text-center">Loading structure...</p>
        )}
        {structure.length > 0 && (
          <div className="max-h-80 overflow-y-auto">
            {structure.map((heading, index) => (
              <div
                key={index}
                className="flex items-center justify-between px-3 py-2.5 rounded-lg hover:bg-[#00ff41]/[0.03] transition-colors"
              >
                <span className="text-sm text-[#8ab88a] truncate">{heading.heading_text}</span>
                <span className="text-xs text-[#2a4a2a] tabular-nums shrink-0 ml-3">p.{heading.page_number}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

export default ChunksViewer

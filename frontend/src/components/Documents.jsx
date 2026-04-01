import { useState, useEffect, useRef, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { getDocuments, getIndexes, createIndex, deleteIndex, deleteDocument, uploadDocument } from '../api/client'

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

function formatDate(iso) {
  return new Date(iso).toLocaleDateString()
}

function slugify(text) {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '')
    .slice(0, 100)
}

function stripPrefix(path, slug) {
  if (path.startsWith(slug + '/')) return path.slice(slug.length + 1)
  return path
}

function Documents({ onSelectDocument, selectedDocumentId }) {
  const navigate = useNavigate()
  const [indexes, setIndexes] = useState([])
  const [allDocuments, setAllDocuments] = useState([])
  const [expandedFolders, setExpandedFolders] = useState({})
  const [uploadingSlug, setUploadingSlug] = useState(null)
  const [uploadStatus, setUploadStatus] = useState(null)
  const fileInputRef = useRef(null)
  const pollRef = useRef(null)

  // Create-index form state
  const [creating, setCreating] = useState(false)
  const [newName, setNewName] = useState('')
  const [newSlug, setNewSlug] = useState('')
  const [slugEdited, setSlugEdited] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)

  const fetchAll = async () => {
    try {
      const [idxData, docData] = await Promise.all([getIndexes(), getDocuments()])
      setIndexes(idxData)
      setAllDocuments(docData.documents || [])
      // Expand all folders on first load
      setExpandedFolders(prev => {
        const next = { ...prev }
        idxData.forEach(idx => {
          if (!(idx.slug in next)) next[idx.slug] = true
        })
        return next
      })
    } catch (err) {
      console.error('Failed to fetch documents/indexes:', err)
    }
  }

  useEffect(() => {
    fetchAll()

    // Auto-refresh when ingestion pipeline reports a completed job
    const handleIngestionComplete = () => fetchAll()
    window.addEventListener('ingestion-complete', handleIngestionComplete)

    return () => {
      if (pollRef.current) clearInterval(pollRef.current)
      window.removeEventListener('ingestion-complete', handleIngestionComplete)
    }
  }, [])

  // Group documents by index slug
  const documentsByIndex = useMemo(() => {
    const grouped = {}
    indexes.forEach(idx => { grouped[idx.slug] = [] })
    allDocuments.forEach(doc => {
      const idx = indexes.find(i => i.display_name === doc.index_name)
      if (idx) {
        grouped[idx.slug]?.push(doc)
      } else {
        // Fallback: try matching by path prefix
        const match = indexes.find(i => doc.path?.startsWith(i.slug + '/'))
        if (match) grouped[match.slug]?.push(doc)
        else (grouped['_unmatched'] ??= []).push(doc)
      }
    })
    return grouped
  }, [indexes, allDocuments])

  const toggleFolder = (slug) => {
    setExpandedFolders(prev => ({ ...prev, [slug]: !prev[slug] }))
  }

  const handleUploadClick = (slug) => {
    setUploadingSlug(slug)
    fileInputRef.current?.click()
  }

  const handleUpload = async (e) => {
    const file = e.target.files?.[0]
    if (!file || !uploadingSlug) return

    const targetSlug = uploadingSlug
    setUploadStatus({ slug: targetSlug, state: 'uploading' })

    try {
      const result = await uploadDocument(file, targetSlug)
      const type = result.status === 'known' ? 'info' : 'success'
      setUploadStatus({ slug: targetSlug, state: type, message: result.message })

      if (result.status === 'queued') {
        const countBefore = allDocuments.length
        let elapsed = 0
        if (pollRef.current) clearInterval(pollRef.current)
        pollRef.current = setInterval(async () => {
          elapsed += 10
          const data = await getDocuments().catch(() => null)
          if (data && data.documents.length > countBefore) {
            setAllDocuments(data.documents)
            setUploadStatus({ slug: targetSlug, state: 'success', message: 'Document ingested and ready' })
            clearInterval(pollRef.current)
            pollRef.current = null
            setTimeout(() => setUploadStatus(null), 4000)
          } else if (elapsed >= 90) {
            clearInterval(pollRef.current)
            pollRef.current = null
          }
        }, 10000)
      } else {
        setTimeout(() => setUploadStatus(null), 5000)
      }
    } catch (err) {
      setUploadStatus({ slug: targetSlug, state: 'error', message: err.message })
      setTimeout(() => setUploadStatus(null), 5000)
    }

    if (fileInputRef.current) fileInputRef.current.value = ''
    setUploadingSlug(null)
  }

  const handleNameChange = (value) => {
    setNewName(value)
    if (!slugEdited) setNewSlug(slugify(value))
  }

  const handleCreate = async () => {
    const slug = newSlug || slugify(newName)
    if (!slug || !newName.trim()) return
    setSubmitting(true)
    setError(null)
    try {
      await createIndex(slug, newName.trim())
      setCreating(false)
      setNewName('')
      setNewSlug('')
      setSlugEdited(false)
      await fetchAll()
    } catch (err) {
      setError(err.message)
    }
    setSubmitting(false)
  }

  const handleDelete = async (slug) => {
    try {
      await deleteIndex(slug)
      await fetchAll()
    } catch (err) {
      setError(err.message)
      setTimeout(() => setError(null), 4000)
    }
  }

  // Document deletion with confirmation
  const [confirmDeleteDoc, setConfirmDeleteDoc] = useState(null)
  const [deletingDoc, setDeletingDoc] = useState(false)

  const handleDeleteDoc = async (docId) => {
    setDeletingDoc(true)
    try {
      await deleteDocument(docId)
      if (selectedDocumentId === docId) onSelectDocument(null)
      setConfirmDeleteDoc(null)
      await fetchAll()
    } catch (err) {
      setError(err.message)
      setTimeout(() => setError(null), 4000)
    }
    setDeletingDoc(false)
  }

  const totalDocs = allDocuments.length

  return (
    <div className="bg-[#0a0f0a] rounded-xl shadow-lg shadow-black/20 overflow-hidden">
      {/* Header */}
      <div className="px-6 pt-5 pb-4 flex items-center justify-between">
        <h2 className="text-xs font-medium text-[#3d6b3d] uppercase tracking-wider">Documents</h2>
        <div className="flex items-center gap-3">
          <span className="text-xs text-[#2a4a2a] tabular-nums">{totalDocs}</span>
          <button
            onClick={() => { setCreating(!creating); setError(null) }}
            className={`px-2.5 py-1 text-xs font-medium rounded-md border transition-colors ${
              creating
                ? 'border-[#00ff41]/40 bg-[#00ff41]/[0.06] text-[#00ff41]'
                : 'border-[#1a3a1a] text-[#8ab88a] hover:bg-[#00ff41]/[0.04] hover:border-[#00ff41]/40'
            }`}
          >
            + New Index
          </button>
        </div>
      </div>

      {/* Hidden file input shared across all folders */}
      <input
        ref={fileInputRef}
        type="file"
        accept=".pdf,.txt,.md,.docx,.html,.xlsx,.pptx"
        onChange={handleUpload}
        className="hidden"
      />

      {/* Inline create-index form */}
      {creating && (
        <div className="mx-6 mb-3 p-3 rounded-lg border border-[#0d2b0d] bg-[#00ff41]/[0.01] flex items-end gap-3">
          <div className="flex-1">
            <label className="text-[11px] font-medium text-[#3d6b3d] uppercase tracking-wider mb-1.5 block">
              Name
            </label>
            <input
              value={newName}
              onChange={(e) => handleNameChange(e.target.value)}
              placeholder="e.g. HR Policies"
              className="w-full h-8 px-2.5 text-xs rounded-md bg-[#00ff41]/[0.03] border border-[#0d2b0d] text-[#c8e6c8] placeholder:text-[#3d6b3d] focus:outline-none focus:ring-1 focus:ring-[#00ff41]/50"
              onKeyDown={(e) => e.key === 'Enter' && handleCreate()}
              autoFocus
            />
          </div>
          <div className="w-32">
            <label className="text-[11px] font-medium text-[#3d6b3d] uppercase tracking-wider mb-1.5 block">
              Slug
            </label>
            <input
              value={newSlug}
              onChange={(e) => { setNewSlug(e.target.value); setSlugEdited(true) }}
              placeholder="hr-policies"
              className="w-full h-8 px-2.5 text-xs rounded-md bg-[#00ff41]/[0.03] border border-[#0d2b0d] text-[#c8e6c8] placeholder:text-[#3d6b3d] focus:outline-none focus:ring-1 focus:ring-[#00ff41]/50 font-mono"
              onKeyDown={(e) => e.key === 'Enter' && handleCreate()}
            />
          </div>
          <button
            onClick={handleCreate}
            disabled={submitting || !newName.trim()}
            className="h-8 px-4 text-xs font-medium rounded-md bg-[#00ff41] text-black hover:bg-[#00cc33] disabled:opacity-50 transition-colors whitespace-nowrap"
          >
            {submitting ? 'Creating...' : 'Create'}
          </button>
          <button
            onClick={() => { setCreating(false); setError(null) }}
            className="h-8 px-3 text-xs font-medium rounded-md border border-[#0d2b0d] text-[#3d6b3d] hover:text-[#8ab88a] transition-colors"
          >
            Cancel
          </button>
        </div>
      )}

      {/* Error display */}
      {error && (
        <div className="mx-6 mb-3 px-3 py-2 rounded-lg bg-red-500/10 text-red-400 text-xs">
          {error}
        </div>
      )}

      {/* Folder tree */}
      <div className="px-3 pb-3">
        {indexes.map(idx => {
          const docs = documentsByIndex[idx.slug] || []
          const expanded = expandedFolders[idx.slug] ?? true
          const isUploading = uploadStatus?.slug === idx.slug && uploadStatus?.state === 'uploading'
          const statusForFolder = uploadStatus?.slug === idx.slug ? uploadStatus : null

          return (
            <div key={idx.slug} className="mb-1">
              {/* Folder header */}
              <div
                className="flex items-center justify-between px-3 py-2 rounded-lg hover:bg-[#00ff41]/[0.03] cursor-pointer group"
                onClick={() => toggleFolder(idx.slug)}
              >
                <div className="flex items-center gap-2 min-w-0">
                  <svg
                    className={`w-3 h-3 text-[#3d6b3d] transition-transform flex-shrink-0 ${expanded ? 'rotate-90' : ''}`}
                    fill="currentColor" viewBox="0 0 20 20"
                  >
                    <path fillRule="evenodd" d="M7.21 14.77a.75.75 0 01.02-1.06L11.168 10 7.23 6.29a.75.75 0 111.04-1.08l4.5 4.25a.75.75 0 010 1.08l-4.5 4.25a.75.75 0 01-1.06-.02z" clipRule="evenodd" />
                  </svg>
                  <span className="text-sm text-[#c8e6c8]">
                    {expanded ? '📂' : '📁'}
                  </span>
                  <span className="text-sm font-medium text-[#c8e6c8] truncate">
                    {idx.display_name}
                  </span>
                  <span className="text-xs text-[#2a4a2a] tabular-nums flex-shrink-0">
                    ({docs.length})
                  </span>
                </div>
                <div className="flex items-center gap-1.5 opacity-0 group-hover:opacity-100 transition-opacity">
                  <button
                    onClick={(e) => { e.stopPropagation(); handleUploadClick(idx.slug) }}
                    disabled={isUploading}
                    className="px-2 py-0.5 text-[11px] font-medium rounded border border-[#1a3a1a] text-[#8ab88a] hover:bg-[#00ff41]/[0.06] hover:border-[#00ff41]/40 transition-colors disabled:opacity-50"
                    title={`Upload to ${idx.display_name}`}
                  >
                    {isUploading ? '...' : '↑'}
                  </button>
                  {idx.slug !== 'default' && docs.length === 0 && (
                    <button
                      onClick={(e) => { e.stopPropagation(); handleDelete(idx.slug) }}
                      className="px-2 py-0.5 text-[11px] font-medium rounded border border-[#1a3a1a] text-[#3d6b3d] hover:text-red-400 hover:border-red-400/40 transition-colors"
                      title="Delete empty index"
                    >
                      ✕
                    </button>
                  )}
                </div>
              </div>

              {/* Upload status for this folder */}
              {statusForFolder && statusForFolder.state !== 'uploading' && (
                <div className={`mx-3 mb-1 px-3 py-1.5 rounded-lg text-xs ${
                  statusForFolder.state === 'error'
                    ? 'bg-red-500/10 text-red-400'
                    : statusForFolder.state === 'info'
                      ? 'bg-[#00e5ff]/10 text-[#00e5ff]'
                      : 'bg-emerald-500/10 text-emerald-400'
                }`}>
                  {statusForFolder.message}
                </div>
              )}

              {/* Document rows */}
              {expanded && (
                <div className="ml-5">
                  {docs.map(doc => (
                    <div
                      key={doc.id}
                      className={`flex items-center justify-between px-3 py-2 rounded-lg cursor-pointer transition-colors group/doc ${
                        selectedDocumentId === doc.id
                          ? 'bg-[#00ff41]/[0.04] border-l-2 border-[#00ff41] pl-2.5'
                          : 'hover:bg-[#00ff41]/[0.03] border-l-2 border-transparent'
                      }`}
                    >
                      <div
                        className="min-w-0 flex-1"
                        onClick={() => {
                          onSelectDocument(doc.id)
                          navigate(`/documents/${doc.id}`)
                        }}
                      >
                        <p className="text-sm text-[#c8e6c8] truncate">
                          {stripPrefix(doc.path, idx.slug)}
                        </p>
                        <p className="text-xs text-[#3d6b3d] mt-0.5">
                          {formatBytes(doc.file_size)}
                          <span className="text-[#1a3a1a] mx-1.5">·</span>
                          {doc.chunk_count} chunks
                          <span className="text-[#1a3a1a] mx-1.5">·</span>
                          {formatDate(doc.ingested_at)}
                        </p>
                      </div>
                      <button
                        onClick={(e) => { e.stopPropagation(); setConfirmDeleteDoc(doc) }}
                        className="p-1 rounded opacity-0 group-hover/doc:opacity-100 text-[#3d6b3d] hover:text-red-400 transition-all flex-shrink-0"
                        title="Delete document"
                      >
                        <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                        </svg>
                      </button>
                    </div>
                  ))}
                  {docs.length === 0 && (
                    <p className="text-xs text-[#2a4a2a] px-3 py-2 italic">Empty — upload a document</p>
                  )}
                </div>
              )}
            </div>
          )
        })}

        {/* Documents that didn't match any index */}
        {(documentsByIndex['_unmatched']?.length > 0) && (
          <div className="mb-1">
            <div className="px-3 py-2 text-xs text-[#2a4a2a]">Unmatched</div>
            <div className="ml-5">
              {documentsByIndex['_unmatched'].map(doc => (
                <div
                  key={doc.id}
                  onClick={() => {
                    onSelectDocument(doc.id)
                    navigate(`/documents/${doc.id}`)
                  }}
                  className="flex items-center px-3 py-2 rounded-lg cursor-pointer hover:bg-[#00ff41]/[0.03] border-l-2 border-transparent"
                >
                  <div className="min-w-0">
                    <p className="text-sm text-[#c8e6c8] truncate">{doc.path}</p>
                    <p className="text-xs text-[#3d6b3d] mt-0.5">
                      {formatBytes(doc.file_size)}
                      <span className="text-[#1a3a1a] mx-1.5">·</span>
                      {doc.chunk_count} chunks
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {indexes.length === 0 && allDocuments.length === 0 && (
          <p className="text-sm text-[#3d6b3d] px-3 py-6 text-center">No documents found</p>
        )}
      </div>

      {/* Delete confirmation dialog */}
      {confirmDeleteDoc && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={() => setConfirmDeleteDoc(null)}>
          <div className="bg-[#0a0f0a] border border-[#0d2b0d] rounded-xl p-5 max-w-sm mx-4 shadow-2xl" onClick={(e) => e.stopPropagation()}>
            <p className="text-sm text-[#c8e6c8] mb-1">Are you sure?</p>
            <p className="text-xs text-[#3d6b3d] mb-4">
              This will permanently delete <span className="text-[#c8e6c8] font-medium">{confirmDeleteDoc.path?.split('/').pop()}</span> and all its chunks, embeddings, and extracted data.
            </p>
            <div className="flex justify-end gap-2">
              <button
                onClick={() => setConfirmDeleteDoc(null)}
                disabled={deletingDoc}
                className="h-8 px-3 text-xs font-medium rounded-md border border-[#0d2b0d] text-[#3d6b3d] hover:text-[#8ab88a] transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={() => handleDeleteDoc(confirmDeleteDoc.id)}
                disabled={deletingDoc}
                className="h-8 px-4 text-xs font-medium rounded-md bg-red-500/20 text-red-400 border border-red-500/30 hover:bg-red-500/30 disabled:opacity-50 transition-colors"
              >
                {deletingDoc ? 'Deleting...' : 'Delete'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default Documents

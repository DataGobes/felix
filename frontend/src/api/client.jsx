const API_URL = import.meta.env.VITE_API_URL || '/api'

export const getMetrics = async () => {
  const response = await fetch(`${API_URL}/metrics`)
  return response.json()
}

export const getIndexes = async () => {
  const response = await fetch(`${API_URL}/indexes`)
  return response.json()
}

export const createIndex = async (slug, displayName, description) => {
  const response = await fetch(`${API_URL}/indexes`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ slug, display_name: displayName, description }),
  })
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Failed to create index' }))
    throw new Error(error.detail || 'Failed to create index')
  }
  return response.json()
}

export const deleteIndex = async (slug) => {
  const response = await fetch(`${API_URL}/indexes/${slug}`, { method: 'DELETE' })
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Failed to delete index' }))
    throw new Error(error.detail || 'Failed to delete index')
  }
  return response.json()
}

export const getDocuments = async (indexSlug) => {
  const params = indexSlug ? `?index_slug=${encodeURIComponent(indexSlug)}` : ''
  const response = await fetch(`${API_URL}/documents${params}`)
  return response.json()
}

export const searchDocuments = async (query, options = {}) => {
  const { searchMode, topK, threshold, includeImages, includeTables, documentIds, indexSlug } = options
  const body = { query }
  if (searchMode) body.search_mode = searchMode
  if (topK != null) body.top_k = topK
  if (threshold != null) body.threshold = threshold
  if (includeImages) body.include_images = true
  if (includeTables) body.include_tables = true
  if (documentIds?.length) body.document_ids = documentIds
  if (indexSlug) body.index_slug = indexSlug
  const response = await fetch(`${API_URL}/search`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return response.json()
}

export const getChunks = async (id) => {
  const response = await fetch(`${API_URL}/documents/${id}/chunks`)
  return response.json()
}

export const getDocumentStructure = async (id) => {
  const response = await fetch(`${API_URL}/documents/${id}/structure`)
  return response.json()
}

export const getDocumentPages = async (id) => {
  const response = await fetch(`${API_URL}/documents/${id}/pages`)
  return response.json()
}

export const getPageElements = async (pageId, { includeText = false } = {}) => {
  const params = includeText ? '?include_text=true' : ''
  const response = await fetch(`${API_URL}/pages/${pageId}/elements${params}`)
  return response.json()
}

export const getImageUrl = (imageId) => `${API_URL}/images/${imageId}/file`

export const getChunkElements = async (chunkId) => {
  const response = await fetch(`${API_URL}/chunks/${chunkId}/elements`)
  return response.json()
}

export const getChunk = async (chunkId) => {
  const response = await fetch(`${API_URL}/chunks/${chunkId}`)
  return response.json()
}

export const getChunkImages = async (chunkId) => {
  const response = await fetch(`${API_URL}/chunks/${chunkId}/images`)
  return response.json()
}

export const getChunkTables = async (chunkId) => {
  const response = await fetch(`${API_URL}/chunks/${chunkId}/tables`)
  return response.json()
}

export const getImage = async (imageId) => {
  const response = await fetch(`${API_URL}/images/${imageId}`)
  return response.json()
}

export const uploadDocument = async (file, indexSlug) => {
  const formData = new FormData()
  formData.append('file', file)
  if (indexSlug) formData.append('index_slug', indexSlug)
  const response = await fetch(`${API_URL}/upload`, { method: 'POST', body: formData })
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Upload failed' }))
    throw new Error(error.detail || 'Upload failed')
  }
  return response.json()
}

export const deleteDocument = async (id) => {
  const response = await fetch(`${API_URL}/documents/${id}`, { method: 'DELETE' })
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Failed to delete document' }))
    throw new Error(error.detail || 'Failed to delete document')
  }
  return response.json()
}

export const getDocument = async (id) => {
  const response = await fetch(`${API_URL}/documents/${id}/detail`)
  return response.json()
}

export const getDocumentTables = async (id) => {
  const response = await fetch(`${API_URL}/documents/${id}/tables`)
  return response.json()
}

export const getDocumentImages = async (id) => {
  const response = await fetch(`${API_URL}/documents/${id}/images`)
  return response.json()
}

export const getImageDuplicates = async () => {
  const response = await fetch(`${API_URL}/images/duplicates`)
  return response.json()
}

export const searchElements = async (documentId, { elementType, limit = 200 } = {}) => {
  const params = new URLSearchParams({ document_id: documentId, limit })
  if (elementType) params.set('element_type', elementType)
  const response = await fetch(`${API_URL}/elements/search?${params}`)
  return response.json()
}

export const getConfig = async () => {
  const response = await fetch(`${API_URL}/config`)
  return response.json()
}

export const updateConfig = async (updates) => {
  const response = await fetch(`${API_URL}/config`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(updates),
  })
  return response.json()
}

export const getIngestionStatus = async (indexSlug) => {
  const params = indexSlug ? `?index_slug=${encodeURIComponent(indexSlug)}` : ''
  const response = await fetch(`${API_URL}/ingestion/status${params}`)
  return response.json()
}

export const INGESTION_STREAM_URL = `${API_URL}/ingestion/stream`

export async function* streamChat(message, history = [], indexSlug = null) {
  const body = { message, history }
  if (indexSlug) body.index_slug = indexSlug
  const response = await fetch(`${API_URL}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!response.ok) {
    throw new Error(`Chat request failed: ${response.status}`)
  }
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop()
    for (const line of lines) {
      if (line.startsWith('data: ')) {
        try {
          yield JSON.parse(line.slice(6))
        } catch {}
      }
    }
  }
  if (buffer.startsWith('data: ')) {
    try {
      yield JSON.parse(buffer.slice(6))
    } catch {}
  }
}

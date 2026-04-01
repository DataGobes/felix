import { useState, useEffect, useMemo } from 'react'
import { searchDocuments, getDocuments } from '../api/client'

const SEARCH_MODES = [
  { value: 'vector', label: 'Vector' },
  { value: 'keyword', label: 'Keyword' },
  { value: 'hybrid', label: 'Hybrid' },
]

function Search() {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [searching, setSearching] = useState(false)
  const [meta, setMeta] = useState(null)
  const [filtersOpen, setFiltersOpen] = useState(false)

  // Filter state
  const [searchMode, setSearchMode] = useState('vector')
  const [topK, setTopK] = useState(5)
  const [threshold, setThreshold] = useState(0)
  const [includeImages, setIncludeImages] = useState(false)
  const [includeTables, setIncludeTables] = useState(false)
  const [selectedDocIds, setSelectedDocIds] = useState([])

  // Documents for filter chips
  const [documents, setDocuments] = useState([])

  useEffect(() => {
    getDocuments()
      .then(data => setDocuments(data.documents || []))
      .catch(() => {})
  }, [])

  const activeFilterCount = useMemo(() => {
    let count = 0
    if (searchMode !== 'vector') count++
    if (topK !== 5) count++
    if (threshold > 0) count++
    if (includeImages) count++
    if (includeTables) count++
    if (selectedDocIds.length > 0) count++
    return count
  }, [searchMode, topK, threshold, includeImages, includeTables, selectedDocIds])

  const handleSearch = async () => {
    if (!query) return
    setSearching(true)
    try {
      const data = await searchDocuments(query, {
        searchMode,
        topK,
        threshold,
        includeImages,
        includeTables,
        documentIds: selectedDocIds.length > 0 ? selectedDocIds : undefined,
      })
      const safeResults = data.results.map(r => ({
        ...r,
        headings: r.headings ?? [],
        images: r.images ?? [],
        tables: r.tables ?? [],
      }))
      setResults(safeResults)
      setMeta({
        total: data.total_results,
        model: data.embedding_model,
        mode: data.search_mode,
      })
    } catch (error) {
      console.error('Search failed:', error)
    }
    setSearching(false)
  }

  const toggleDocId = (id) => {
    setSelectedDocIds(prev =>
      prev.includes(id) ? prev.filter(d => d !== id) : [...prev, id]
    )
  }

  const formatScore = (result) => {
    const mode = meta?.mode || searchMode
    if (mode === 'hybrid') {
      return `RRF ${result.similarity.toFixed(4)}`
    }
    if (mode === 'keyword') {
      return `rank ${result.similarity.toFixed(3)}`
    }
    return `${(result.similarity * 100).toFixed(1)}%`
  }

  return (
    <div className="bg-white rounded-xl shadow-sm overflow-hidden">
      {/* Header */}
      <div className="px-6 pt-5 pb-4 flex items-center justify-between">
        <h2 className="text-xs font-medium text-warm-500 uppercase tracking-wider">Search</h2>
        {meta && (
          <div className="flex items-center gap-2">
            {meta.mode && (
              <span className="px-1.5 py-0.5 text-[10px] font-medium rounded bg-ember/[0.08] text-ember uppercase">
                {meta.mode}
              </span>
            )}
            <span className="text-xs text-warm-400 tabular-nums">
              {meta.total} results
            </span>
          </div>
        )}
      </div>

      <div className="px-6 pb-5 space-y-3">
        {/* Search bar row */}
        <div className="flex gap-2">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search your documents..."
            onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
            className="flex-1 h-9 px-3 text-sm rounded-lg bg-warm-bg border border-warm-200 text-warm-900 placeholder:text-warm-500 focus:outline-none focus:ring-1 focus:ring-ember/50 transition-colors"
          />
          <button
            onClick={() => setFiltersOpen(!filtersOpen)}
            className={`h-9 px-3 text-xs font-medium rounded-lg border transition-colors flex items-center gap-1.5 ${
              filtersOpen
                ? 'border-ember/40 bg-ember/[0.08] text-ember'
                : 'border-warm-200 text-warm-500 hover:text-warm-900 hover:border-warm-200'
            }`}
          >
            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M10.5 6h9.75M10.5 6a1.5 1.5 0 11-3 0m3 0a1.5 1.5 0 10-3 0M3.75 6H7.5m3 12h9.75m-9.75 0a1.5 1.5 0 01-3 0m3 0a1.5 1.5 0 00-3 0m-3.75 0H7.5m9-6h3.75m-3.75 0a1.5 1.5 0 01-3 0m3 0a1.5 1.5 0 00-3 0m-9.75 0h9.75" />
            </svg>
            Filters
            {activeFilterCount > 0 && (
              <span className="w-4 h-4 rounded-full bg-ember text-white text-[10px] font-bold flex items-center justify-center">
                {activeFilterCount}
              </span>
            )}
          </button>
          <button
            onClick={handleSearch}
            disabled={searching}
            className="h-9 px-4 text-xs font-medium rounded-lg bg-ember text-white hover:bg-ember/90 disabled:opacity-50 transition-colors"
          >
            {searching ? 'Searching...' : 'Search'}
          </button>
        </div>

        {/* Collapsible filters panel */}
        {filtersOpen && (
          <div className="p-4 rounded-lg border border-warm-200 bg-warm-100 space-y-4">
            {/* Search Mode */}
            <div>
              <label className="text-[11px] font-medium text-warm-500 uppercase tracking-wider mb-2 block">
                Search Mode
              </label>
              <div className="flex gap-1.5">
                {SEARCH_MODES.map(mode => (
                  <button
                    key={mode.value}
                    onClick={() => setSearchMode(mode.value)}
                    className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
                      searchMode === mode.value
                        ? 'bg-ember text-white'
                        : 'bg-ember/[0.04] text-warm-500 hover:text-warm-900 border border-warm-200'
                    }`}
                  >
                    {mode.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Number inputs row */}
            <div className="flex gap-4">
              <div className="flex-1">
                <label className="text-[11px] font-medium text-warm-500 uppercase tracking-wider mb-2 block">
                  Results (top_k)
                </label>
                <input
                  type="number"
                  min={1}
                  max={50}
                  value={topK}
                  onChange={(e) => setTopK(Math.min(50, Math.max(1, parseInt(e.target.value) || 1)))}
                  className="w-full h-8 px-2.5 text-xs rounded-md bg-warm-bg border border-warm-200 text-warm-900 focus:outline-none focus:ring-1 focus:ring-ember/50 tabular-nums"
                />
              </div>
              <div className="flex-1">
                <label className="text-[11px] font-medium text-warm-500 uppercase tracking-wider mb-2 block">
                  Threshold
                </label>
                <input
                  type="number"
                  min={0}
                  max={1}
                  step={0.05}
                  value={threshold}
                  onChange={(e) => setThreshold(Math.min(1, Math.max(0, parseFloat(e.target.value) || 0)))}
                  className="w-full h-8 px-2.5 text-xs rounded-md bg-warm-bg border border-warm-200 text-warm-900 focus:outline-none focus:ring-1 focus:ring-ember/50 tabular-nums"
                />
              </div>
            </div>

            {/* Include checkboxes */}
            <div className="flex gap-4">
              <label className="flex items-center gap-2 cursor-pointer group">
                <input
                  type="checkbox"
                  checked={includeImages}
                  onChange={(e) => setIncludeImages(e.target.checked)}
                  className="sr-only peer"
                />
                <div className="w-4 h-4 rounded border border-warm-200 bg-warm-bg peer-checked:bg-ember peer-checked:border-ember flex items-center justify-center transition-colors">
                  {includeImages && (
                    <svg className="w-2.5 h-2.5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                    </svg>
                  )}
                </div>
                <span className="text-xs text-warm-500 group-hover:text-warm-900 transition-colors">
                  Include images
                </span>
              </label>
              <label className="flex items-center gap-2 cursor-pointer group">
                <input
                  type="checkbox"
                  checked={includeTables}
                  onChange={(e) => setIncludeTables(e.target.checked)}
                  className="sr-only peer"
                />
                <div className="w-4 h-4 rounded border border-warm-200 bg-warm-bg peer-checked:bg-ember peer-checked:border-ember flex items-center justify-center transition-colors">
                  {includeTables && (
                    <svg className="w-2.5 h-2.5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                    </svg>
                  )}
                </div>
                <span className="text-xs text-warm-500 group-hover:text-warm-900 transition-colors">
                  Include tables
                </span>
              </label>
            </div>

            {/* Document filter */}
            {documents.length > 0 && (
              <div>
                <label className="text-[11px] font-medium text-warm-500 uppercase tracking-wider mb-2 block">
                  Filter by document
                  {selectedDocIds.length > 0 && (
                    <button
                      onClick={() => setSelectedDocIds([])}
                      className="ml-2 text-[10px] text-ember/60 hover:text-ember normal-case tracking-normal"
                    >
                      clear
                    </button>
                  )}
                </label>
                <div className="flex flex-wrap gap-1.5">
                  {documents.map(doc => {
                    const selected = selectedDocIds.includes(doc.id)
                    const name = doc.path.split('/').pop()
                    return (
                      <button
                        key={doc.id}
                        onClick={() => toggleDocId(doc.id)}
                        className={`px-2 py-1 text-[11px] rounded-md transition-colors truncate max-w-[180px] ${
                          selected
                            ? 'bg-ember/[0.12] text-ember border border-ember/40'
                            : 'bg-warm-bg text-warm-500 border border-warm-200 hover:text-warm-900 hover:border-warm-200'
                        }`}
                        title={doc.path}
                      >
                        {name}
                      </button>
                    )
                  })}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Results */}
        <div className="space-y-2">
          {results.map(result => (
            <div key={result.chunk_id} className="p-4 rounded-lg bg-warm-100 border border-warm-200 space-y-2.5">
              <div className="flex items-center justify-between">
                <span className="text-xs text-warm-500">
                  {result.document_path}
                  {result.index_name && (
                    <span className="ml-1.5 px-1.5 py-0.5 text-[10px] font-medium rounded bg-ember/[0.08] text-ember/70">
                      {result.index_name}
                    </span>
                  )}
                </span>
                <span className="text-xs font-medium text-ember tabular-nums">
                  {formatScore(result)}
                </span>
              </div>
              {result.headings.length > 0 && (
                <p className="text-xs text-warm-600">{result.headings.join(' > ')}</p>
              )}
              <p className="text-sm text-warm-900 leading-relaxed">{result.content}</p>
              <div className="flex gap-3 text-[11px] text-warm-400">
                <span>chunk {result.chunk_index}</span>
                <span>{result.token_count} tokens</span>
                {result.tables.length > 0 && (
                  <span className="text-amber-600">{result.tables.length} table{result.tables.length > 1 ? 's' : ''}</span>
                )}
                {result.images.length > 0 && (
                  <span className="text-purple-600">{result.images.length} image{result.images.length > 1 ? 's' : ''}</span>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

export default Search

import { useState, useEffect, useCallback } from 'react'
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { useNavigate } from 'react-router-dom'
import { getIndexes, getWikiPages, getWikiPage, buildWiki } from '../api/client'
import useWikiBuild from '../hooks/useWikiBuild'
import { ScrollArea } from '@/components/ui/scroll-area'

const CITATION_RE = /\[Felix:chunk:(\d+)\]/g

function Wiki() {
  const [indexSlug, setIndexSlug] = useState('default')
  const [indexes, setIndexes] = useState([])
  const [pages, setPages] = useState([])
  const [selected, setSelected] = useState(null)
  const [page, setPage] = useState(null)
  const navigate = useNavigate()
  const { job } = useWikiBuild(indexSlug)

  useEffect(() => { getIndexes().then(d => setIndexes(d || [])).catch(() => {}) }, [])

  const loadPages = useCallback(() => {
    getWikiPages(indexSlug).then(d => setPages(d.pages || [])).catch(() => {})
  }, [indexSlug])

  useEffect(() => { loadPages() }, [loadPages])
  useEffect(() => {
    if (job?.status === 'completed') loadPages()
  }, [job?.status, loadPages])

  const openPage = async (slug) => {
    setSelected(slug)
    const data = await getWikiPage(indexSlug, slug)
    setPage(data)
  }

  const renderBody = (md) => {
    if (!md) return md
    const body = md.replace(/^---\n[\s\S]*?\n---\n*/, '')
    return body.replace(CITATION_RE, (_, n) => `[\`chunk:${n}\`](#chunk-${n})`)
                .replace(/\[\[([^\]]+)\]\]/g, (_, s) => `[${s}](#wiki-${s})`)
  }

  const onLinkClick = (href) => {
    if (href?.startsWith('#wiki-')) { openPage(href.slice(6)); return false }
    if (href?.startsWith('#chunk-')) { navigate(`/documents/1?chunk=${href.slice(7)}`); return false }
    return true
  }

  const byType = pages.reduce((acc, p) => {
    (acc[p.type] ||= []).push(p); return acc
  }, {})

  return (
    <div className="max-w-6xl mx-auto px-6 py-8">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-lg font-semibold text-warm-900">Wiki</h1>
          <p className="text-xs text-warm-500 mt-0.5">Autonomously built from your index</p>
        </div>
        <div className="flex items-center gap-2">
          <select value={indexSlug} onChange={e => setIndexSlug(e.target.value)}
            className="text-xs border border-warm-200 rounded-md px-2 py-1.5">
            {indexes.map(i => <option key={i.slug} value={i.slug}>{i.display_name || i.slug}</option>)}
          </select>
          <button onClick={() => buildWiki(indexSlug)}
            className="px-3 py-1.5 text-xs font-medium rounded-md bg-ember text-white hover:opacity-90">
            Build Wiki
          </button>
        </div>
      </div>

      {job && job.status && job.status !== 'completed' && job.status !== 'none' && (
        <div className="mb-4 text-xs text-ember">Building… {job.status}
          {job.progress?.pages ? ` (${job.progress.pages} pages)` : ''}</div>
      )}

      <div className="grid gap-6 grid-cols-1 lg:grid-cols-4">
        <div className="bg-white rounded-xl shadow-sm overflow-hidden">
          <div className="px-6 pt-5 pb-4">
            <h2 className="text-xs font-medium text-warm-500 uppercase tracking-wider">Pages</h2>
          </div>
          <ScrollArea className="h-[28rem]">
            <div className="px-3 pb-3 space-y-3">
              {Object.entries(byType).map(([type, group]) => (
                <div key={type}>
                  <div className="px-3 text-[10px] uppercase tracking-wider text-warm-400">{type}</div>
                  {group.map(p => (
                    <button key={p.slug} onClick={() => openPage(p.slug)}
                      className={`w-full text-left px-3 py-2 text-xs rounded-lg transition-colors ${
                        selected === p.slug ? 'text-ember bg-ember/[0.08]'
                          : 'text-warm-600 hover:text-warm-900 hover:bg-warm-50'}`}>
                      {p.title}
                    </button>
                  ))}
                </div>
              ))}
              {pages.length === 0 && (
                <p className="text-sm text-warm-500 px-3 py-6 text-center">
                  No wiki yet. Click &quot;Build Wiki&quot;.</p>
              )}
            </div>
          </ScrollArea>
        </div>

        <div className="lg:col-span-3 bg-white rounded-xl shadow-sm overflow-hidden">
          {!selected && (
            <div className="px-6 py-12 text-center">
              <p className="text-sm text-warm-500">Select a page to view</p>
            </div>
          )}
          {selected && page && (
            <div className="px-6 py-6 prose prose-sm max-w-none">
              <Markdown remarkPlugins={[remarkGfm]} components={{
                a: ({ href, children }) => (
                  <a href={href} onClick={(e) => { if (onLinkClick(href) === false) e.preventDefault() }}>
                    {children}
                  </a>
                ),
              }}>
                {renderBody(page.content_md)}
              </Markdown>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default Wiki

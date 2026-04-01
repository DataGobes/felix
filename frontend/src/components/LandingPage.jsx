import { Link } from 'react-router-dom'
import Footer from './Footer'

const FEATURES = [
  { icon: '↑', title: 'Document Ingestion', desc: 'Automatic conversion via Docling with real-time progress streaming.' },
  { icon: '⊕', title: 'Semantic Search', desc: 'Vector similarity search over document chunks using pgvector.' },
  { icon: '💬', title: 'AI Chat', desc: 'Conversational Q&A over your corpus with source citations.' },
  { icon: '▤', title: 'Layout Analysis', desc: 'Bounding boxes, element types, page-level spatial metadata.' },
  { icon: '⊞', title: 'Table Extraction', desc: 'Structured table data with cell-level detail and deduplication.' },
  { icon: '☰', title: 'Structure Navigation', desc: 'Browse document hierarchy, headings, and reading order.' },
]

const FORMATS = ['PDF', 'DOCX', 'PPTX', 'XLSX', 'TXT', 'Markdown']

const TECH = [
  { name: 'Docling', desc: 'Document conversion' },
  { name: 'pgvector', desc: 'Vector embeddings' },
  { name: 'FastAPI', desc: 'Search & chat API' },
  { name: 'React', desc: 'Frontend' },
]

function LandingPage() {
  return (
    <div className="min-h-screen flex flex-col bg-warm-bg">
      {/* Header */}
      <header className="bg-white border-b border-warm-200 px-6 h-14 flex-shrink-0 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <img src="/felix-logo.svg" alt="Felix" className="w-7 h-7" />
          <span className="text-sm font-semibold text-warm-900">Felix</span>
        </div>
        <Link
          to="/documents"
          className="bg-ember text-white px-4 py-1.5 rounded-md text-xs font-medium hover:bg-ember/90 transition-colors"
        >
          Get Started
        </Link>
      </header>

      {/* Hero */}
      <section className="py-20 px-6 text-center">
        <div className="max-w-xl mx-auto">
          <div className="w-14 h-14 rounded-xl bg-[#0d0d0d] flex items-center justify-center mx-auto mb-6">
            <span className="text-ember text-xl font-bold font-mono">&gt;_</span>
          </div>
          <h1 className="text-3xl font-bold text-warm-900 leading-tight mb-4">
            Document Intelligence<br />for your business
          </h1>
          <p className="text-warm-500 text-base leading-relaxed mb-8 max-w-md mx-auto">
            Upload any document — Felix decomposes it into structured elements,
            generates semantic embeddings, and provides search and AI chat over your corpus.
          </p>
          <div className="flex gap-3 justify-center">
            <Link
              to="/documents"
              className="bg-ember text-white px-5 py-2 rounded-md text-sm font-medium hover:bg-ember/90 transition-colors"
            >
              Get Started
            </Link>
            <a
              href="#features"
              className="border border-warm-200 text-warm-500 px-5 py-2 rounded-md text-sm font-medium hover:text-warm-900 hover:border-warm-400 transition-colors"
            >
              Learn More
            </a>
          </div>
        </div>
      </section>

      {/* Features */}
      <section id="features" className="py-16 px-6 border-t border-warm-200">
        <div className="max-w-3xl mx-auto">
          <p className="text-ember text-[10px] font-semibold uppercase tracking-[2px] text-center mb-2">Features</p>
          <h2 className="text-xl font-semibold text-warm-900 text-center mb-10">Everything you need</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {FEATURES.map(f => (
              <div key={f.title} className="bg-white border border-warm-200 rounded-lg p-5">
                <div className="w-8 h-8 rounded-md bg-ember/[0.08] flex items-center justify-center mb-3">
                  <span className="text-ember text-sm">{f.icon}</span>
                </div>
                <h3 className="text-sm font-semibold text-warm-900 mb-1">{f.title}</h3>
                <p className="text-xs text-warm-500 leading-relaxed">{f.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Formats */}
      <section className="py-12 px-6 border-t border-warm-200">
        <div className="max-w-3xl mx-auto text-center">
          <p className="text-ember text-[10px] font-semibold uppercase tracking-[2px] mb-4">Supported Formats</p>
          <div className="flex gap-2 justify-center flex-wrap">
            {FORMATS.map(f => (
              <span key={f} className="bg-white border border-warm-200 rounded-md px-3.5 py-1.5 text-sm font-medium text-warm-900">
                {f}
              </span>
            ))}
          </div>
        </div>
      </section>

      {/* Tech Stack */}
      <section className="py-12 px-6 border-t border-warm-200">
        <div className="max-w-3xl mx-auto text-center">
          <p className="text-ember text-[10px] font-semibold uppercase tracking-[2px] mb-4">Built With</p>
          <div className="flex gap-6 justify-center flex-wrap">
            {TECH.map(t => (
              <div key={t.name} className="text-center">
                <p className="text-sm font-medium text-warm-900">{t.name}</p>
                <p className="text-xs text-warm-400">{t.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Footer */}
      <div className="mt-auto">
        <Footer />
      </div>
    </div>
  )
}

export default LandingPage

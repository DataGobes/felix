import { useState } from 'react'
import { Routes, Route, Link, Outlet, useLocation } from 'react-router-dom'
import MetricsBar from './components/MetricsBar'
import Documents from './components/Documents'
import Search from './components/Search'
import Chat from './components/Chat'
import ChunksViewer from './components/ChunksViewer'
import ControlPanel from './components/ControlPanel'
import DocumentViewer from './pages/DocumentViewer'
import MatrixRain from './components/MatrixRain'
import IngestionPipeline from './components/IngestionPipeline'

function Shell() {
  const location = useLocation()

  return (
    <div className="h-screen flex flex-col bg-[#050505] text-[#c8e6c8] relative">
      <MatrixRain />
      {/* Header */}
      <header className="border-b border-[#0d2b0d] px-6 h-14 flex-shrink-0 flex items-center justify-between relative z-10">
        <div className="flex items-center gap-6">
          <Link to="/" className="flex items-center gap-2.5 hover:opacity-80 transition-opacity">
            <div className="w-7 h-7 rounded bg-[#00ff41]/20 border border-[#00ff41]/40 flex items-center justify-center">
              <span className="text-[#00ff41] text-sm font-bold">F</span>
            </div>
            <span className="text-sm font-bold text-[#00ff41] tracking-widest uppercase"
                  style={{ animation: 'glitch 3s infinite' }}>
              Felix
            </span>
          </Link>
          <nav className="flex items-center gap-1">
            <Link
              to="/"
              className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
                location.pathname === '/'
                  ? 'text-[#00ff41] bg-[#00ff41]/10'
                  : 'text-[#3d6b3d] hover:text-[#8ab88a]'
              }`}
            >
              Dashboard
            </Link>
            <Link
              to="/settings"
              className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
                location.pathname === '/settings'
                  ? 'text-[#00ff41] bg-[#00ff41]/10'
                  : 'text-[#3d6b3d] hover:text-[#8ab88a]'
              }`}
            >
              Settings
            </Link>
          </nav>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-xs text-[#3d6b3d]">Document Intelligence</span>
        </div>
      </header>

      {/* Metrics Bar */}
      <div className="relative z-10">
        <MetricsBar />
      </div>

      {/* Main Content */}
      <main className="flex-1 min-h-0 overflow-auto relative z-10">
        <Outlet />
      </main>
    </div>
  )
}

function DashboardContent() {
  const [selectedDocumentId, setSelectedDocumentId] = useState(null)
  const [mode, setMode] = useState('search')

  return (
    <div className="max-w-[1800px] mx-auto px-6 py-6">
      <IngestionPipeline />
      <div className="flex items-center gap-1.5 mb-4">
        <button
          onClick={() => setMode('search')}
          className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
            mode === 'search'
              ? 'bg-[#00ff41] text-black'
              : 'bg-[#00ff41]/[0.04] text-[#3d6b3d] hover:text-[#8ab88a] border border-[#0d2b0d]'
          }`}
        >
          Search
        </button>
        <button
          onClick={() => setMode('chat')}
          className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
            mode === 'chat'
              ? 'bg-[#00ff41] text-black'
              : 'bg-[#00ff41]/[0.04] text-[#3d6b3d] hover:text-[#8ab88a] border border-[#0d2b0d]'
          }`}
        >
          Chat
        </button>
      </div>
      <div className={`grid gap-6 ${
        selectedDocumentId
          ? 'grid-cols-1 lg:grid-cols-[1fr_1fr_1fr]'
          : 'grid-cols-1 lg:grid-cols-2'
      }`}>
        <Documents onSelectDocument={setSelectedDocumentId} selectedDocumentId={selectedDocumentId} />
        {mode === 'search' ? <Search /> : <Chat />}
        {selectedDocumentId && (
          <ChunksViewer selectedDocumentId={selectedDocumentId} />
        )}
      </div>
    </div>
  )
}

function SettingsContent() {
  return (
    <div className="max-w-[1800px] mx-auto px-6 py-6">
      <ControlPanel />
    </div>
  )
}

function App() {
  return (
    <Routes>
      <Route element={<Shell />}>
        <Route path="/" element={<DashboardContent />} />
        <Route path="/settings" element={<SettingsContent />} />
      </Route>
      <Route path="/documents/:id" element={<DocumentViewer />} />
    </Routes>
  )
}

export default App

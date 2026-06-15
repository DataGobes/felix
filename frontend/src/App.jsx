import { useState } from 'react'
import { Routes, Route } from 'react-router-dom'
import LandingPage from './components/LandingPage'
import AppShell from './components/AppShell'
import Documents from './components/Documents'
import Search from './components/Search'
import Chat from './components/Chat'
import Wiki from './components/Wiki'
import ChunksViewer from './components/ChunksViewer'
import ControlPanel from './components/ControlPanel'
import DocumentViewer from './pages/DocumentViewer'
import IngestionPipeline from './components/IngestionPipeline'

function DocumentsPage() {
  const [selectedDocumentId, setSelectedDocumentId] = useState(null)

  return (
    <div className="max-w-5xl mx-auto px-6 py-8">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-lg font-semibold text-warm-900">Documents</h1>
          <p className="text-xs text-warm-500 mt-0.5">Manage your document corpus</p>
        </div>
      </div>
      <IngestionPipeline />
      <div className={`grid gap-6 ${
        selectedDocumentId ? 'grid-cols-1 lg:grid-cols-2' : 'grid-cols-1'
      }`}>
        <Documents onSelectDocument={setSelectedDocumentId} selectedDocumentId={selectedDocumentId} />
        {selectedDocumentId && (
          <ChunksViewer selectedDocumentId={selectedDocumentId} />
        )}
      </div>
    </div>
  )
}

function SearchPage() {
  return (
    <div className="max-w-3xl mx-auto px-6 py-8">
      <div className="mb-6">
        <h1 className="text-lg font-semibold text-warm-900">Search</h1>
        <p className="text-xs text-warm-500 mt-0.5">Semantic search across your documents</p>
      </div>
      <Search />
    </div>
  )
}

function ChatPage() {
  return (
    <div className="max-w-3xl mx-auto px-6 py-8 h-full">
      <Chat />
    </div>
  )
}

function WikiPage() {
  return (
    <Wiki />
  )
}

function SettingsPage() {
  return (
    <div className="max-w-3xl mx-auto px-6 py-8">
      <div className="mb-6">
        <h1 className="text-lg font-semibold text-warm-900">Settings</h1>
        <p className="text-xs text-warm-500 mt-0.5">Configure document enrichment pipeline</p>
      </div>
      <ControlPanel />
    </div>
  )
}

function App() {
  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route element={<AppShell />}>
        <Route path="/documents" element={<DocumentsPage />} />
        <Route path="/search" element={<SearchPage />} />
        <Route path="/wiki" element={<WikiPage />} />
        <Route path="/chat" element={<ChatPage />} />
        <Route path="/settings" element={<SettingsPage />} />
      </Route>
      <Route path="/documents/:id" element={<DocumentViewer />} />
    </Routes>
  )
}

export default App

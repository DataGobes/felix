# Felix Ember Light Retheme — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Retheme Felix from Matrix/cyberpunk to Ember Light (datagobes.dev brand) with a landing page, multi-page routing, and footer watermark — ready for a LinkedIn portfolio showcase.

**Architecture:** Skin swap across all frontend components — replace Matrix green palette with Ember Light warm tones, restructure routing from single-page dashboard to multi-page app (landing, documents, search, chat), add LandingPage, AppShell, and Footer components.

**Tech Stack:** React 19, Tailwind CSS 3, Geist fonts (CDN), react-router-dom 7

---

## File Structure

```
frontend/src/
├── App.jsx                    # MODIFY: new routing structure
├── index.css                  # MODIFY: replace CSS variables + remove Matrix effects
├── components/
│   ├── LandingPage.jsx        # NEW: landing page with hero, features, formats
│   ├── AppShell.jsx           # NEW: shared layout (header + footer) for app pages
│   ├── Footer.jsx             # NEW: datagobes.dev watermark
│   ├── Documents.jsx          # MODIFY: color swap
│   ├── Search.jsx             # MODIFY: color swap
│   ├── Chat.jsx               # MODIFY: color swap
│   ├── ChunksViewer.jsx       # MODIFY: color swap
│   ├── ControlPanel.jsx       # MODIFY: color swap
│   ├── IngestionPipeline.jsx  # MODIFY: color swap + remove glow animations
│   ├── MatrixRain.jsx         # DELETE
│   ├── MetricsBar.jsx         # DELETE
│   └── ui/*.jsx               # MODIFY: update CSS variable references
frontend/
├── index.html                 # MODIFY: add Geist font CDN links
├── tailwind.config.js         # MODIFY: add Ember color tokens
├── public/felix-logo.svg      # KEEP: already uses #c75c2c
```

---

### Task 1: Foundation — CSS variables, Tailwind config, fonts, cleanup

**Files:**
- Modify: `frontend/src/index.css`
- Modify: `frontend/tailwind.config.js`
- Modify: `frontend/index.html`
- Delete: `frontend/src/components/MatrixRain.jsx`
- Delete: `frontend/src/components/MetricsBar.jsx`
- Delete: `frontend/src/App.css`

- [ ] **Step 1: Replace index.css with Ember Light theme**

Replace the entire contents of `frontend/src/index.css` with:

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

@layer base {
  :root {
    --background: 30 14% 97%;
    --foreground: 25 10% 10%;
    --card: 0 0% 100%;
    --card-foreground: 25 10% 10%;
    --popover: 0 0% 100%;
    --popover-foreground: 25 10% 10%;
    --primary: 18 64% 48%;
    --primary-foreground: 0 0% 100%;
    --secondary: 30 8% 95%;
    --secondary-foreground: 25 10% 10%;
    --muted: 30 8% 95%;
    --muted-foreground: 25 7% 56%;
    --accent: 30 8% 95%;
    --accent-foreground: 25 10% 10%;
    --destructive: 0 84% 60%;
    --destructive-foreground: 0 0% 98%;
    --border: 30 10% 90%;
    --input: 30 10% 90%;
    --ring: 18 64% 48%;
    --radius: 0.75rem;
  }

  * {
    border-color: hsl(var(--border));
  }

  body {
    background-color: #faf9f7;
    color: #1a1816;
    font-feature-settings: "rlig" 1, "calt" 1;
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
  }
}

/* Chat: typing indicator dots */
@keyframes typing-dot {
  0%, 60%, 100% { opacity: 0.3; }
  30% { opacity: 1; }
}

.typing-dot {
  animation: typing-dot 1.4s infinite;
}
```

- [ ] **Step 2: Add Ember color tokens to tailwind.config.js**

Replace the entire contents of `frontend/tailwind.config.js` with:

```js
/** @type {import('tailwindcss').Config} */
export default {
    darkMode: ["class"],
    content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      borderRadius: {
        lg: 'var(--radius)',
        md: 'calc(var(--radius) - 2px)',
        sm: 'calc(var(--radius) - 4px)'
      },
      colors: {
        ember: '#c75c2c',
        'warm-bg': '#faf9f7',
        'warm-900': '#1a1816',
        'warm-600': '#5c5347',
        'warm-500': '#9a9184',
        'warm-400': '#b5ada4',
        'warm-200': '#e8e4df',
        'warm-100': '#f3f1ee',
        background: 'hsl(var(--background))',
        foreground: 'hsl(var(--foreground))',
        card: {
          DEFAULT: 'hsl(var(--card))',
          foreground: 'hsl(var(--card-foreground))'
        },
        popover: {
          DEFAULT: 'hsl(var(--popover))',
          foreground: 'hsl(var(--popover-foreground))'
        },
        primary: {
          DEFAULT: 'hsl(var(--primary))',
          foreground: 'hsl(var(--primary-foreground))'
        },
        secondary: {
          DEFAULT: 'hsl(var(--secondary))',
          foreground: 'hsl(var(--secondary-foreground))'
        },
        muted: {
          DEFAULT: 'hsl(var(--muted))',
          foreground: 'hsl(var(--muted-foreground))'
        },
        accent: {
          DEFAULT: 'hsl(var(--accent))',
          foreground: 'hsl(var(--accent-foreground))'
        },
        destructive: {
          DEFAULT: 'hsl(var(--destructive))',
          foreground: 'hsl(var(--destructive-foreground))'
        },
        border: 'hsl(var(--border))',
        input: 'hsl(var(--input))',
        ring: 'hsl(var(--ring))',
        chart: {
          '1': 'hsl(var(--chart-1))',
          '2': 'hsl(var(--chart-2))',
          '3': 'hsl(var(--chart-3))',
          '4': 'hsl(var(--chart-4))',
          '5': 'hsl(var(--chart-5))'
        }
      }
    }
  },
  plugins: [require("tailwindcss-animate")],
}
```

- [ ] **Step 3: Add Geist fonts to index.html**

In `frontend/index.html`, add these lines inside `<head>`, before the closing `</head>` tag:

```html
    <link rel="preconnect" href="https://cdn.jsdelivr.net" crossorigin>
    <link href="https://cdn.jsdelivr.net/fontsource/fonts/geist-sans@latest/latin-400-normal.woff2" as="font" type="font/woff2" crossorigin>
    <link href="https://cdn.jsdelivr.net/fontsource/fonts/geist-sans@latest/latin.min.css" rel="stylesheet">
    <link href="https://cdn.jsdelivr.net/fontsource/fonts/geist-mono@latest/latin.min.css" rel="stylesheet">
```

Also update the `body` styles by adding to `index.css` body rule (already done in Step 1 — the font is applied via CSS, not index.html):

Update the body rule in `index.css` to include font-family:

```css
  body {
    background-color: #faf9f7;
    color: #1a1816;
    font-family: 'Geist Sans', 'Geist', system-ui, -apple-system, sans-serif;
    font-feature-settings: "rlig" 1, "calt" 1;
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
  }
```

- [ ] **Step 4: Delete MatrixRain.jsx, MetricsBar.jsx, App.css**

```bash
rm frontend/src/components/MatrixRain.jsx
rm frontend/src/components/MetricsBar.jsx
rm frontend/src/App.css
```

- [ ] **Step 5: Verify Tailwind builds without errors**

```bash
cd frontend && npm run build 2>&1 | tail -5
```

Expected: Build succeeds (may have warnings about unused imports in App.jsx — that's fine, we fix those in Task 2).

- [ ] **Step 6: Commit**

```bash
cd ~/Projects/felix
git add frontend/src/index.css frontend/tailwind.config.js frontend/index.html
git add -u frontend/src/components/MatrixRain.jsx frontend/src/components/MetricsBar.jsx frontend/src/App.css
git commit -m "feat: replace Matrix theme with Ember Light foundation"
```

---

### Task 2: New components — Footer, AppShell, LandingPage

**Files:**
- Create: `frontend/src/components/Footer.jsx`
- Create: `frontend/src/components/AppShell.jsx`
- Create: `frontend/src/components/LandingPage.jsx`

- [ ] **Step 1: Create Footer.jsx**

Write `frontend/src/components/Footer.jsx`:

```jsx
function Footer() {
  return (
    <footer className="border-t border-warm-200 px-6 py-4 flex items-center justify-end gap-2">
      <div className="w-4 h-4 rounded bg-[#0d0d0d] flex items-center justify-center flex-shrink-0">
        <span className="text-[7px] font-bold text-ember font-mono">&gt;_</span>
      </div>
      <span className="text-xs text-warm-400">
        Built by <span className="text-warm-500">datagobes.dev</span>
      </span>
    </footer>
  )
}

export default Footer
```

- [ ] **Step 2: Create AppShell.jsx**

Write `frontend/src/components/AppShell.jsx`:

```jsx
import { Link, Outlet, useLocation } from 'react-router-dom'
import Footer from './Footer'

const NAV_ITEMS = [
  { to: '/documents', label: 'Documents' },
  { to: '/search', label: 'Search' },
  { to: '/chat', label: 'Chat' },
]

function AppShell() {
  const location = useLocation()

  return (
    <div className="h-screen flex flex-col bg-warm-bg">
      <header className="bg-white border-b border-warm-200 px-6 h-14 flex-shrink-0 flex items-center justify-between">
        <div className="flex items-center gap-6">
          <Link to="/" className="flex items-center gap-2.5 hover:opacity-80 transition-opacity">
            <img src="/felix-logo.svg" alt="Felix" className="w-7 h-7" />
            <span className="text-sm font-semibold text-warm-900">Felix</span>
          </Link>
          <nav className="flex items-center gap-1">
            {NAV_ITEMS.map(item => (
              <Link
                key={item.to}
                to={item.to}
                className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
                  location.pathname.startsWith(item.to)
                    ? 'text-ember bg-ember/[0.08]'
                    : 'text-warm-500 hover:text-warm-900'
                }`}
              >
                {item.label}
              </Link>
            ))}
          </nav>
        </div>
        <Link
          to="/settings"
          className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
            location.pathname === '/settings'
              ? 'text-ember bg-ember/[0.08]'
              : 'text-warm-500 hover:text-warm-900'
          }`}
        >
          Settings
        </Link>
      </header>

      <main className="flex-1 min-h-0 overflow-auto">
        <Outlet />
      </main>

      <Footer />
    </div>
  )
}

export default AppShell
```

- [ ] **Step 3: Create LandingPage.jsx**

Write `frontend/src/components/LandingPage.jsx`:

```jsx
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
```

- [ ] **Step 4: Commit**

```bash
cd ~/Projects/felix
git add frontend/src/components/Footer.jsx frontend/src/components/AppShell.jsx frontend/src/components/LandingPage.jsx
git commit -m "feat: add LandingPage, AppShell, and Footer components"
```

---

### Task 3: Rewrite App.jsx routing

**Files:**
- Modify: `frontend/src/App.jsx`

- [ ] **Step 1: Replace App.jsx with new routing structure**

Replace the entire contents of `frontend/src/App.jsx` with:

```jsx
import { useState } from 'react'
import { Routes, Route } from 'react-router-dom'
import LandingPage from './components/LandingPage'
import AppShell from './components/AppShell'
import Documents from './components/Documents'
import Search from './components/Search'
import Chat from './components/Chat'
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
        <Route path="/chat" element={<ChatPage />} />
        <Route path="/settings" element={<SettingsPage />} />
      </Route>
      <Route path="/documents/:id" element={<DocumentViewer />} />
    </Routes>
  )
}

export default App
```

- [ ] **Step 2: Verify build compiles**

```bash
cd frontend && npm run build 2>&1 | tail -5
```

Expected: Build succeeds. The app now has landing page at `/`, app pages at `/documents`, `/search`, `/chat`, `/settings`.

- [ ] **Step 3: Commit**

```bash
cd ~/Projects/felix
git add frontend/src/App.jsx
git commit -m "feat: restructure routing to multi-page with landing page"
```

---

### Task 4: Retheme Documents.jsx

**Files:**
- Modify: `frontend/src/components/Documents.jsx`

- [ ] **Step 1: Color swap Documents.jsx**

Apply these find-and-replace operations across the entire `frontend/src/components/Documents.jsx` file:

| Find | Replace |
|------|---------|
| `bg-[#0a0f0a]` | `bg-white` |
| `shadow-lg shadow-black/20` | `shadow-sm` |
| `text-[#3d6b3d]` | `text-warm-500` |
| `text-[#2a4a2a]` | `text-warm-400` |
| `text-[#c8e6c8]` | `text-warm-900` |
| `text-[#8ab88a]` | `text-warm-900` |
| `border-[#0d2b0d]` | `border-warm-200` |
| `border-[#1a3a1a]` | `border-warm-200` |
| `text-[#1a3a1a]` | `text-warm-200` |
| `bg-[#00ff41]/[0.06]` | `bg-ember/[0.08]` |
| `bg-[#00ff41]/[0.04]` | `bg-ember/[0.04]` |
| `bg-[#00ff41]/[0.03]` | `bg-warm-bg` |
| `bg-[#00ff41]/[0.01]` | `bg-warm-100` |
| `border-[#00ff41]/40` | `border-ember/40` |
| `border-[#00ff41]` | `border-ember` |
| `text-[#00ff41]` | `text-ember` |
| `bg-[#00ff41]` | `bg-ember` |
| `hover:bg-[#00cc33]` | `hover:bg-ember/90` |
| `text-black` | `text-white` |
| `ring-[#00ff41]/50` | `ring-ember/50` |
| `bg-[#00e5ff]/10 text-[#00e5ff]` | `bg-blue-50 text-blue-600` |
| `bg-emerald-500/10 text-emerald-400` | `bg-emerald-50 text-emerald-600` |
| `bg-red-500/10 text-red-400` | `bg-red-50 text-red-600` |
| `hover:text-red-400` | `hover:text-red-600` |
| `hover:border-red-400/40` | `hover:border-red-300` |
| `bg-red-500/20` | `bg-red-50` |
| `border-red-500/30` | `border-red-200` |
| `hover:bg-red-500/30` | `hover:bg-red-100` |
| `bg-black/60` | `bg-black/40` |
| `shadow-2xl` | `shadow-lg` |

Also in the delete confirmation dialog, update the modal background:
- `bg-[#0a0f0a] border border-[#0d2b0d]` → `bg-white border border-warm-200`

- [ ] **Step 2: Verify no Matrix colors remain**

```bash
grep -n "#00ff41\|#0a0f0a\|#050505\|#0d2b0d\|#3d6b3d\|#c8e6c8\|#8ab88a\|#2a4a2a\|#1a3a1a\|#00cc33\|#00e5ff" frontend/src/components/Documents.jsx
```

Expected: No matches.

- [ ] **Step 3: Commit**

```bash
cd ~/Projects/felix
git add frontend/src/components/Documents.jsx
git commit -m "feat: retheme Documents component to Ember Light"
```

---

### Task 5: Retheme Search.jsx

**Files:**
- Modify: `frontend/src/components/Search.jsx`

- [ ] **Step 1: Color swap Search.jsx**

Apply these find-and-replace operations across `frontend/src/components/Search.jsx`:

| Find | Replace |
|------|---------|
| `bg-[#0a0f0a]` | `bg-white` |
| `shadow-lg shadow-black/20` | `shadow-sm` |
| `text-[#3d6b3d]` | `text-warm-500` |
| `text-[#2a4a2a]` | `text-warm-400` |
| `text-[#c8e6c8]` | `text-warm-900` |
| `text-[#8ab88a]` | `text-warm-900` |
| `border-[#0d2b0d]` | `border-warm-200` |
| `border-[#1a3a1a]` | `border-warm-200` |
| `bg-[#00ff41]/[0.06]` | `bg-ember/[0.08]` |
| `bg-[#00ff41]/[0.04]` | `bg-ember/[0.04]` |
| `bg-[#00ff41]/[0.03]` | `bg-warm-bg` |
| `bg-[#00ff41]/[0.02]` | `bg-warm-100` |
| `bg-[#00ff41]/[0.01]` | `bg-warm-100` |
| `border-[#00ff41]/40` | `border-ember/40` |
| `text-[#00ff41]` | `text-ember` |
| `bg-[#00ff41]` | `bg-ember` |
| `text-black` | `text-white` |
| `hover:bg-[#00cc33]` | `hover:bg-ember/90` |
| `ring-[#00ff41]/50` | `ring-ember/50` |
| `bg-[#00ff41]/10` | `bg-ember/[0.08]` |
| `bg-[#00ff41]/20` | `bg-ember/[0.12]` |
| `text-[#00ff41]/70` | `text-ember/70` |
| `text-[#00ff41]/60` | `text-ember/60` |
| `text-[#00e5ff]/80` | `text-warm-600` |
| `peer-checked:bg-[#00ff41]` | `peer-checked:bg-ember` |
| `peer-checked:border-[#00ff41]` | `peer-checked:border-ember` |
| `text-amber-500/70` | `text-amber-600` |
| `text-purple-400/70` | `text-purple-600` |

- [ ] **Step 2: Verify no Matrix colors remain**

```bash
grep -n "#00ff41\|#0a0f0a\|#050505\|#0d2b0d\|#3d6b3d\|#c8e6c8\|#8ab88a\|#2a4a2a\|#1a3a1a\|#00cc33\|#00e5ff" frontend/src/components/Search.jsx
```

Expected: No matches.

- [ ] **Step 3: Commit**

```bash
cd ~/Projects/felix
git add frontend/src/components/Search.jsx
git commit -m "feat: retheme Search component to Ember Light"
```

---

### Task 6: Retheme Chat.jsx

**Files:**
- Modify: `frontend/src/components/Chat.jsx`

- [ ] **Step 1: Color swap Chat.jsx**

Apply these find-and-replace operations across `frontend/src/components/Chat.jsx`:

| Find | Replace |
|------|---------|
| `bg-[#0a0f0a]` | `bg-white` |
| `shadow-lg shadow-black/20` | `shadow-sm` |
| `text-[#3d6b3d]` | `text-warm-500` |
| `text-[#2a4a2a]` | `text-warm-400` |
| `text-[#c8e6c8]` | `text-warm-900` |
| `text-[#8ab88a]` | `text-warm-600` |
| `border-[#0d2b0d]` | `border-warm-200` |
| `bg-[#00ff41]/[0.06]` | `bg-ember/[0.06]` |
| `bg-[#00ff41]/[0.03]` | `bg-warm-bg` |
| `bg-[#00ff41]/[0.02]` | `bg-warm-100` |
| `border-[#00ff41]/20` | `border-ember/20` |
| `border-[#00ff41]/40` | `border-ember/40` |
| `text-[#00ff41]` | `text-ember` |
| `bg-[#00ff41]` | `bg-ember` |
| `text-black` | `text-white` |
| `hover:bg-[#00cc33]` | `hover:bg-ember/90` |
| `ring-[#00ff41]/50` | `ring-ember/50` |
| `bg-[#00ff41]/10` | `bg-ember/[0.08]` |
| `bg-[#00ff41]/30` | `bg-ember/30` |
| `text-[#00ff41]/60` | `text-ember/60` |
| `text-[#00e5ff]/70` | `text-warm-600` |
| `text-red-400/80` | `text-red-600` |
| `bg-[#1a1a1a]` | `bg-warm-200` |
| `bg-[#3d6b3d]` | `bg-warm-400` |

- [ ] **Step 2: Verify no Matrix colors remain**

```bash
grep -n "#00ff41\|#0a0f0a\|#050505\|#0d2b0d\|#3d6b3d\|#c8e6c8\|#8ab88a\|#2a4a2a\|#1a3a1a\|#00cc33\|#00e5ff\|#1a1a1a" frontend/src/components/Chat.jsx
```

Expected: No matches.

- [ ] **Step 3: Commit**

```bash
cd ~/Projects/felix
git add frontend/src/components/Chat.jsx
git commit -m "feat: retheme Chat component to Ember Light"
```

---

### Task 7: Retheme IngestionPipeline.jsx

**Files:**
- Modify: `frontend/src/components/IngestionPipeline.jsx`

- [ ] **Step 1: Color swap IngestionPipeline.jsx**

Apply these find-and-replace operations across `frontend/src/components/IngestionPipeline.jsx`:

| Find | Replace |
|------|---------|
| `bg-[#00ff41]` | `bg-ember` |
| `border-[#00ff41]` | `border-ember` |
| `shadow-[0_0_6px_rgba(0,255,65,0.4)]` | `` (remove — no glow) |
| `bg-[#00ff41]/20` | `bg-ember/20` |
| `pipeline-pulse` | `` (remove — no pulse animation) |
| `shadow-[0_0_6px_rgba(239,68,68,0.4)]` | `` (remove — no glow) |
| `bg-[#0a0f0a]` | `bg-warm-bg` |
| `border-[#1a3a1a]` | `border-warm-200` |
| `text-[#00ff41]` | `text-ember` |
| `text-[#2a4a2a]` | `text-warm-400` |
| `text-[#c8e6c8]` | `text-warm-900` |
| `text-[#3d6b3d]` | `text-warm-500` |
| `border-[#0d2b0d]` | `border-warm-200` |
| `bg-[#0a0f0a]/80` | `bg-white` |
| `bg-[#00ff41]/60` | `bg-ember/60` |
| `bg-[#00ff41]/30` | `bg-ember/30` |
| `data-flow` | `` (remove — no data flow animation) |
| `bg-[#00ff41]/15` | `bg-ember/[0.08]` |
| `shadow-[0_0_4px_rgba(0,255,65,0.5)]` | `` (remove — no glow) |
| `text-red-400/70` | `text-red-600` |
| `text-red-400/60` | `text-red-500` |
| `text-red-400` | `text-red-600` |
| `bg-red-500/20` | `bg-red-50` |
| `border-red-500` | `border-red-300` |
| `text-amber-400` | `text-amber-600` |
| `bg-amber-500/15` | `bg-amber-50` |

- [ ] **Step 2: Verify no Matrix colors remain**

```bash
grep -n "#00ff41\|#0a0f0a\|#050505\|#0d2b0d\|#3d6b3d\|#c8e6c8\|#2a4a2a\|#1a3a1a\|pipeline-pulse\|data-flow\|shadow-\[0_0" frontend/src/components/IngestionPipeline.jsx
```

Expected: No matches.

- [ ] **Step 3: Commit**

```bash
cd ~/Projects/felix
git add frontend/src/components/IngestionPipeline.jsx
git commit -m "feat: retheme IngestionPipeline to Ember Light"
```

---

### Task 8: Retheme ChunksViewer.jsx and ControlPanel.jsx

**Files:**
- Modify: `frontend/src/components/ChunksViewer.jsx`
- Modify: `frontend/src/components/ControlPanel.jsx`

- [ ] **Step 1: Color swap ChunksViewer.jsx**

Apply these find-and-replace operations across `frontend/src/components/ChunksViewer.jsx`:

| Find | Replace |
|------|---------|
| `bg-[#0a0f0a]` | `bg-white` |
| `shadow-lg shadow-black/20` | `shadow-sm` |
| `text-[#3d6b3d]` | `text-warm-500` |
| `text-[#2a4a2a]` | `text-warm-400` |
| `text-[#8ab88a]` | `text-warm-900` |
| `hover:bg-[#00ff41]/[0.03]` | `hover:bg-warm-100` |

- [ ] **Step 2: Color swap ControlPanel.jsx**

Apply these find-and-replace operations across `frontend/src/components/ControlPanel.jsx`:

| Find | Replace |
|------|---------|
| `bg-[#0a0f0a]` | `bg-white` |
| `shadow-lg shadow-black/20` | `shadow-sm` |
| `text-[#5a8a5a]` | `text-warm-600` |
| `text-[#3d6b3d]` | `text-warm-500` |
| `text-[#2a4a2a]` | `text-warm-400` |
| `text-[#c8e6c8]` | `text-warm-900` |
| `border-[#0d2b0d]` | `border-warm-200` |
| `border-[#1a3a1a]` | `border-warm-200` |
| `bg-[#0d1f0d]` | `bg-warm-bg` |
| `placeholder-[#1e3a1e]` | `placeholder-warm-400` |
| `border-[#00ff41]/60` | `border-ember/60` |
| `bg-[#00ff41]/20` | `bg-ember/20` |
| `border-[#00ff41]/30` | `border-ember/30` |
| `shadow-[0_0_15px_-5px_#00ff4130]` | `` (remove) |
| `shadow-[0_0_8px_#00ff41]` | `` (remove) |
| `bg-[#00ff41]` | `bg-ember` |
| `text-[#00ff41]` | `text-ember` |
| `border-[#00ff41]/40` | `border-ember/40` |
| `ring-[#00ff41]/20` | `ring-ember/20` |
| `ring-[#00ff41]/30` | `ring-ember/30` |
| `border-t-[#00ff41]` | `border-t-ember` |
| `border-[#00ff41]/40` | `border-ember/40` |
| `focus:ring-offset-[#0a0f0a]` | `focus:ring-offset-white` |
| `bg-[#3d6b3d]` | `bg-warm-400` |
| `bg-[#00ff41]/[0.03]` | `bg-warm-bg` |
| `emerald-400` | `emerald-600` |
| `emerald-500/10` | `emerald-50` |
| `bg-red-500/10` | `bg-red-50` |
| `border-red-500/20` | `border-red-200` |
| `text-red-400` | `text-red-600` |

Also update the Pipeline Settings title:
Find: `text-lg font-bold text-[#00ff41] tracking-wider uppercase`
Replace: `text-lg font-semibold text-warm-900`

- [ ] **Step 3: Verify no Matrix colors remain in either file**

```bash
grep -n "#00ff41\|#0a0f0a\|#050505\|#0d2b0d\|#3d6b3d\|#c8e6c8\|#8ab88a\|#5a8a5a\|#2a4a2a\|#1a3a1a\|#0d1f0d\|#1e3a1e" frontend/src/components/ChunksViewer.jsx frontend/src/components/ControlPanel.jsx
```

Expected: No matches.

- [ ] **Step 4: Commit**

```bash
cd ~/Projects/felix
git add frontend/src/components/ChunksViewer.jsx frontend/src/components/ControlPanel.jsx
git commit -m "feat: retheme ChunksViewer and ControlPanel to Ember Light"
```

---

### Task 9: Build, verify, and rebuild Docker image

- [ ] **Step 1: Verify local build compiles**

```bash
cd ~/Projects/felix/frontend && npm run build 2>&1 | tail -10
```

Expected: Build succeeds with no errors.

- [ ] **Step 2: Check no Matrix colors remain anywhere in src/**

```bash
grep -rn "#00ff41\|#050505\|#0a0f0a\|#0d2b0d\|#3d6b3d\|#c8e6c8\|#8ab88a\|#2a4a2a\|#1a3a1a\|#00cc33\|#00e5ff\|#5a8a5a\|#0d1f0d\|MatrixRain\|Share Tech Mono\|glitch\|scanline" frontend/src/ --include="*.jsx" --include="*.css"
```

Expected: No matches (other than possibly comments).

- [ ] **Step 3: Rebuild Docker frontend image and restart**

```bash
cd ~/Projects/felix
docker compose build felix-frontend && docker compose up -d felix-frontend
```

Expected: Frontend rebuilds and restarts.

- [ ] **Step 4: Verify pages load**

```bash
sleep 2
curl -s -o /dev/null -w "Landing: %{http_code}\n" http://localhost:5180/
curl -s -o /dev/null -w "Documents: %{http_code}\n" http://localhost:5180/documents
curl -s -o /dev/null -w "Search: %{http_code}\n" http://localhost:5180/search
curl -s -o /dev/null -w "Chat: %{http_code}\n" http://localhost:5180/chat
```

Expected: All return 200.

- [ ] **Step 5: Visual verification**

Open http://localhost:5180 in browser. Verify:
- Landing page shows with warm off-white background, ember orange accents
- "Get Started" button navigates to /documents
- App header shows Felix logo + Documents/Search/Chat nav
- Footer shows ">_ Built by datagobes.dev"
- No green Matrix colors anywhere
- No MatrixRain animation
- No scanline overlay

- [ ] **Step 6: Commit**

```bash
cd ~/Projects/felix
git add -A
git commit -m "feat: complete Ember Light retheme — ready for portfolio"
```

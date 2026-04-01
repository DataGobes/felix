# Felix Ember Light Retheme — Design Spec

## Goal

Retheme Felix from Matrix/cyberpunk to Ember Light (datagobes.dev brand) for a LinkedIn portfolio piece. The UI itself needs to impress as a professional product showcase.

## Approach

Skin swap — replace all Matrix colors, fonts, and effects with Ember Light palette. Add landing page and footer watermark. Restructure routing to multi-page app. Keep existing component logic untouched.

## Color Palette: Ember Light

| Role | Hex | Tailwind Token | Usage |
|------|-----|----------------|-------|
| Primary accent | `#c75c2c` | `ember` | Buttons, active nav, links, highlights, icons |
| Page background | `#faf9f7` | `warm-bg` | Off-white page background |
| Card surface | `#ffffff` | `white` | Cards sitting on warm-bg |
| Primary text | `#1a1816` | `warm-900` | Headings, body text, filenames |
| Secondary text | `#9a9184` | `warm-500` | Labels, nav items, metadata |
| Muted text | `#b5ada4` | `warm-400` | Placeholders, timestamps, fine print |
| Tertiary text | `#5c5347` | `warm-600` | Fine print, subtle labels |
| Borders | `#e8e4df` | `warm-200` | Card borders, dividers, input borders |
| Input background | `#faf9f7` | `warm-bg` | Inputs sit on white cards, same as page bg |
| Active/hover bg | `rgba(199,92,44,0.08)` | `ember/[0.08]` | Hover rows, active tabs, selected states |
| Logo background | `#0d0d0d` | — | Dark logo mark contrasts on light page |
| Error | `#dc2626` | `red-600` | Error states, failed ingestion |
| Success | `#16a34a` | `green-600` | Completed ingestion, success badges |

### Typography

- **Body:** Geist Sans (CDN)
- **Code/labels:** Geist Mono (CDN)
- **Loaded via:** `<link>` in index.html from CDN

## Routing

| Route | Page | Description |
|-------|------|-------------|
| `/` | Landing page | Hero, features, formats, tech stack, CTA |
| `/documents` | Documents | Document list, upload, index management, ingestion pipeline |
| `/documents/:id` | Document viewer | Existing full-page viewer (PDF, PPTX, XLSX, Text) |
| `/search` | Search | Semantic search with results, filters, mode toggle |
| `/chat` | Chat | AI chat with MiniMax-M2.7, citations, thinking toggle |

## Landing Page

Scrollable showcase at `/`. Sections top to bottom:

1. **Header** — `>_` logo + "Felix" left, "Get Started" button right. White background, border-bottom.
2. **Hero** — large `>_` logo, "Document Intelligence for your business" tagline, one-paragraph description, dual CTA ("Get Started" → `/documents`, "Learn More" → scroll to features).
3. **Features grid** — 6 cards in 2x3 grid on white cards with ember-tinted icon backgrounds:
   - Document Ingestion
   - Semantic Search
   - AI Chat
   - Layout Analysis
   - Table Extraction
   - Structure Navigation
4. **Supported formats** — pill badges: PDF, DOCX, PPTX, XLSX, TXT, Markdown
5. **Tech stack** — Docling, pgvector, FastAPI, React (subtle, below fold)
6. **Footer watermark**

## App Shell

Shared layout wrapping Documents, Search, Chat pages:

- **Header** — white background, border-bottom `#e8e4df`. Left: `>_` logo + "Felix" wordmark. Nav: Documents, Search, Chat. Active nav item uses ember text + `ember/[0.08]` background.
- **Main** — `#faf9f7` background, page title + content in centered container.
- **Footer** — border-top, right-aligned: small `>_` logo + "Built by datagobes.dev" in muted text.

## Documents Page

- Page title "Documents" with document count badge
- Upload button (ember orange, white text)
- Index management (create/delete index)
- Document list as clean rows on white cards — filename, format badge (PDF/DOCX/etc), ingestion date, file size
- Click document → `/documents/:id`
- Ingestion pipeline inline: shows progress when a document is being processed, uses subtle opacity transitions instead of green glow animations

## Search Page

- Large search input at top with ember focus ring
- Mode toggle: semantic / hybrid / keyword (ember active state)
- Results as white cards — document name, heading breadcrumbs, content preview, similarity score
- Filter panel for document/index selection

## Chat Page

- Full-height chat interface
- Header: "MiniMax-M2.7" model badge + thinking toggle
- User messages: subtle ember tint background (`ember/[0.06]`)
- Assistant messages: white card with light border
- Citations collapsed under assistant messages
- Send button: ember orange

## Footer Watermark

Appears on every page including landing page. Right-aligned:
- Small `>_` logo (16x16, dark background)
- "Built by datagobes.dev" in muted text (`#b5ada4`, "datagobes.dev" slightly darker at `#9a9184`)

## Files Changed

### Deleted/gutted
- `MatrixRain.jsx` — already returns null, can delete
- `App.css` — unused Vite boilerplate, delete
- `index.css` — remove all Matrix animations (scanline, glitch, pipeline-pulse, data-flow, graph animations), replace CSS variables

### Modified (color swap)
- `index.css` — new Ember Light CSS variables, remove Matrix effects, update body styles
- `index.html` — add Geist font CDN links
- `tailwind.config.js` — add custom color tokens (ember, warm-bg, warm-200, warm-400, warm-500, warm-600, warm-900)
- `App.jsx` — restructure routing, remove MatrixRain import, update header to app shell
- `Documents.jsx` — swap all Matrix colors to Ember Light equivalents
- `Search.jsx` — swap all Matrix colors to Ember Light equivalents
- `Chat.jsx` — swap all Matrix colors to Ember Light equivalents
- `ChunksViewer.jsx` — swap all Matrix colors
- `ControlPanel.jsx` — swap all Matrix colors
- `IngestionPipeline.jsx` — swap all Matrix colors, replace glow animations with opacity transitions
- `ui/badge.jsx` — update color variants
- `ui/button.jsx` — update color variants
- `ui/card.jsx` — update color variants
- `ui/input.jsx` — update border/focus colors
- `ui/progress.jsx` — update bar color
- `ui/scroll-area.jsx` — update scrollbar colors

### New files
- `LandingPage.jsx` — landing page component
- `Footer.jsx` — datagobes.dev watermark component
- `AppShell.jsx` — shared layout (header nav + footer, wraps app pages)

## Color Mapping Reference

For implementation — find and replace across all components:

| Matrix | Ember Light |
|--------|-------------|
| `bg-[#050505]` | `bg-[#faf9f7]` |
| `bg-[#0a0f0a]` | `bg-white` |
| `border-[#0d2b0d]` | `border-warm-200` |
| `text-[#c8e6c8]` | `text-warm-900` |
| `text-[#3d6b3d]` | `text-warm-500` |
| `text-[#2a4a2a]` | `text-warm-400` |
| `text-[#8ab88a]` | `text-warm-900` |
| `text-[#5a8a5a]` | `text-warm-600` |
| `#00ff41` (all variants) | `ember` (all variants) |
| `#00e5ff` | `ember` (was cyan accent, now just ember) |
| `bg-[#0d1f0d]` | `bg-[#faf9f7]` |
| `border-[#1a3a1a]` | `border-warm-200` |
| `bg-[#00ff41]/10` | `bg-ember/[0.08]` |
| `bg-[#00ff41]/[0.03]` | `bg-[#faf9f7]` |
| `bg-[#00ff41]/[0.04]` | `bg-ember/[0.04]` |
| `bg-[#00ff41]/[0.06]` | `bg-ember/[0.06]` |
| `ring-[#00ff41]/50` | `ring-ember/50` |
| `shadow-*green*` | remove (no glow effects) |

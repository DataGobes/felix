# Felix MCP Server + LLM-Wiki Integration

**Date:** 2026-04-15
**Goal:** Build a Felix MCP server that enables LLM agents to build and maintain structured wikis from documents processed by Felix. Demo with Karpathy's Mythos PDF to create a LinkedIn-ready showcase.

## Context

Andrej Karpathy's llm-wiki concept (April 2026) describes a pattern where LLMs incrementally build persistent wikis from source documents. The weakness: LLMs can't reliably read complex PDFs. Karpathy himself noted this when the 245-page Mythos PDF "failed badly" with mangled output.

Felix solves this by sitting between raw documents and the LLM agent:

```
Raw PDF → Felix (Docling conversion) → Structured API → LLM agent → Wiki
```

## Architecture

### Layer 0: Felix (Document Intelligence)

Felix handles document conversion, chunking, embedding, and structured storage. The LLM never touches raw files — it queries Felix's API for structured content with full reading order, element types, tables, images, and cross-references preserved.

### Layer 1: Felix MCP Server

A Python MCP server (`mcp-server/server.py`) that wraps Felix's REST API as MCP tools. Any MCP-capable agent (Claude Code, Codex, etc.) can use these tools natively.

**Location:** `felix/mcp-server/server.py`
**Tech:** Python, `mcp` SDK (FastMCP), `httpx` for async HTTP
**Config:** `FELIX_API_URL` env var, defaults to `http://localhost:8001`

### Layer 2: Wiki (LLM-generated markdown)

A git repo of markdown files, structured by the schema in CLAUDE.md. The LLM owns this layer — it creates pages, maintains cross-references, and keeps everything consistent.

### Layer 3: Schema (CLAUDE.md)

Instructions that tell the LLM how the wiki is structured, what conventions to follow, and how to use Felix tools for ingest/query/lint operations.

## MCP Server Tools

### Core Tools

| Tool | Felix Endpoint(s) | Description |
|------|-------------------|-------------|
| `felix_list_documents` | `GET /documents` | List all ingested documents with metadata |
| `felix_document_detail` | `GET /documents/{id}/detail` | Full document metadata, page count, element stats |
| `felix_document_structure` | `GET /documents/{id}/structure` | Heading tree (TOC) with reading order and page numbers |
| `felix_read_section` | Composite: structure + page elements | **Key tool.** Read a document section by heading or page range, returning all elements (text, tables, images, footnotes) in reading order |
| `felix_search` | `POST /search` | Semantic search across all documents |
| `felix_get_chunk` | `GET /chunks/{id}` | Single chunk with full content and metadata |
| `felix_get_tables` | `GET /tables` | List tables with optional document filter |
| `felix_get_table` | `GET /tables/{id}` | Single table with markdown/HTML/text content and cell data |
| `felix_get_images` | `GET /images` | List images with optional document filter |
| `felix_upload` | `POST /upload` | Upload a document for ingestion |
| `felix_ingestion_status` | `GET /ingestion/status` | Check processing progress for all jobs |

### `felix_read_section` — Design

This is the compound tool that reconstructs a document section with full structural fidelity.

**Parameters:**
- `document_id` (required): Document to read from
- `heading` (optional): Heading text to match (finds the section starting at this heading, ending at next heading of same or higher level)
- `start_page` / `end_page` (optional): Page range to read (alternative to heading)
- `include_images` (default true): Include image references with captions
- `include_tables` (default true): Include table content as markdown

**Implementation:**
1. Fetch document structure (`GET /documents/{id}/structure`)
2. Determine the page/element range from the heading match or page range
3. Fetch page elements for all pages in range (`GET /pages/{id}/elements?include_text=true`)
4. For tables in range: fetch table content (`GET /tables/{id}`)
5. For images in range: include caption and image_id
6. Assemble all elements in `reading_order`, grouped by page

**Response format:**
```json
{
  "document_id": 1,
  "section": "Chapter 3: The Titans",
  "page_range": [45, 62],
  "elements": [
    {"order": 1, "type": "section_header", "level": 1, "text": "The Titans", "page": 45},
    {"order": 2, "type": "text", "text": "In the beginning there was Chaos...", "page": 45},
    {"order": 3, "type": "picture", "caption": "Figure 3.1", "image_id": 42, "page": 46},
    {"order": 4, "type": "table", "caption": "The Twelve Titans", "table_id": 7, "markdown": "| Name | Domain |...", "page": 48},
    {"order": 5, "type": "footnote", "text": "Some sources list fourteen...", "page": 48}
  ]
}
```

## Wiki Structure

```
mythos-wiki/
├── CLAUDE.md              # Schema — agent operating instructions
├── wiki/
│   ├── index.md           # Content catalog
│   ├── log.md             # Chronological operation log
│   ├── overview.md        # High-level synthesis
│   ├── sources/
│   │   └── mythos.md      # Source summary
│   ├── entities/
│   │   ├── zeus.md        # God/titan/hero pages
│   │   └── ...
│   ├── concepts/
│   │   ├── fate-and-prophecy.md
│   │   └── ...
│   └── chapters/
│       ├── 01-the-beginning.md
│       └── ...
└── raw/
    └── README.md          # "Sources managed by Felix at <url>"
```

## Wiki Schema (CLAUDE.md) — Key Conventions

### Felix connection
The agent uses Felix MCP tools for all document access. No raw file reading.

### Page frontmatter
```yaml
---
title: Zeus
type: entity          # entity | concept | chapter | source | analysis
sources: [mythos]
felix_refs: [chunk:42, chunk:89, table:7]
last_updated: 2026-04-15
---
```

### Cross-references
- Wiki links: `[[entity-name]]` for internal cross-references
- Felix citations: `[Felix:chunk:42]` for traceable source references
- Every factual claim should cite at least one Felix reference

### Ingest workflow
1. `felix_list_documents` → find the document
2. `felix_document_structure` → get full TOC
3. For each major section: `felix_read_section` → structured content
4. Write source summary in `wiki/sources/`
5. Create/update entity pages for significant entities
6. Create/update concept pages for major themes
7. Write chapter summaries with cross-references
8. Update `index.md` and `log.md`

### Query workflow
1. Read `wiki/index.md` for relevant pages
2. If wiki pages suffice → synthesize from wiki
3. If more detail needed → `felix_search`
4. If answer is valuable → file as new wiki page

## Demo Scope (Mythos)

Target 5-10 wiki pages that showcase the pipeline:
- `overview.md` — book summary with structure
- `sources/mythos.md` — source page with Felix metadata
- 2-3 chapter pages showing section reconstruction
- 2-3 entity pages (e.g., Zeus, Kronos, Prometheus) with cross-references
- 1 concept page (e.g., fate and prophecy) synthesized across chapters

## Execution Sequence

### Step 1: Get Felix running
- `docker compose up -d` (CPU mode, no GPU service)
- Remove `platform: linux/amd64` for native ARM performance
- Verify: `curl http://localhost:8001/health`

### Step 2: Acquire and ingest Mythos PDF
- User provides the PDF (copyrighted book)
- Upload via Felix UI or drop in `~/mission-control-ingest/`
- Monitor ingestion via `GET /ingestion/status`

### Step 3: Build Felix MCP server
- Single file: `mcp-server/server.py` (~200-250 lines)
- Dependencies: `mcp`, `httpx`
- Key implementation: `felix_read_section` compound tool
- Register in Claude Code MCP config

### Step 4: Create wiki repo with schema
- Scaffold directory structure
- Write CLAUDE.md schema
- Init git repo

### Step 5: Build wiki using Felix MCP tools
- Use Claude Code with Felix MCP server active
- Walk the book structure, build pages
- Target: 5-10 polished pages with Felix citations

### Step 6: Screenshots + LinkedIn post
- Felix UI: document structure, chunks viewer, search results, tables
- Wiki: rendered markdown pages with cross-references
- Narrative: "Karpathy says PDFs are hard. Here's the solution."

## Not in scope
- GPU/MPS support (follow-up work)
- Batch ingestion of multiple books
- Wiki lint operations
- Embedding-based wiki search (index.md is sufficient at this scale)

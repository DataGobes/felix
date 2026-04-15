# Felix MCP Server + LLM-Wiki Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Felix MCP server that enables LLM agents to query processed documents and build structured wikis, demonstrated with the Mythos PDF.

**Architecture:** A Python MCP server (`FastMCP`) wraps Felix's REST API as tools. The key tool `felix_read_section` composes multiple API calls server-side to return full document sections with interleaved text, tables, images, and footnotes in reading order. A wiki schema (CLAUDE.md) instructs the agent how to use these tools for ingest/query operations.

**Tech Stack:** Python 3.11+, `mcp` SDK (FastMCP), `httpx` (async HTTP), Felix REST API

---

## File Structure

```
felix/
├── mcp-server/
│   ├── server.py          # MCP server — all tools (~250 lines)
│   ├── requirements.txt   # mcp, httpx
│   └── README.md          # Setup and usage instructions
├── llm-wiki/
│   ├── CLAUDE.md          # Wiki schema — agent operating instructions
│   ├── wiki/
│   │   ├── index.md       # Content catalog
│   │   └── log.md         # Operation log
│   └── raw/
│       └── README.md      # Pointer to Felix
└── docker-compose.yml     # Updated: remove platform: linux/amd64 for ARM
```

---

## Task 1: Fix Docker Compose for Apple Silicon

Remove `platform: linux/amd64` from all services so they run natively on ARM64 instead of through Rosetta emulation. This gives better performance on M3 Max.

**Files:**
- Modify: `docker-compose.yml:7,28,59,100` (remove platform lines)

- [ ] **Step 1: Remove platform lines from docker-compose.yml**

Remove the `platform: linux/amd64` line from these services:
- `felix-postgres` (line 7)
- `felix-api` (line 28)  
- `felix-ingestion` (line 59)
- `felix-frontend` (line 100)

Keep it on `felix-gpu` — that one legitimately needs x86_64 for CUDA.

Note: `pgvector/pgvector:pg16` publishes ARM64 images, so this works. The backend Dockerfiles use `python:3.11-slim` which also has ARM64 images.

- [ ] **Step 2: Verify compose config is valid**

Run: `POSTGRES_PASSWORD=test docker compose config --quiet 2>&1 && echo "OK"`
Expected: `OK` (no errors)

- [ ] **Step 3: Commit**

```bash
git add docker-compose.yml
git commit -m "fix: remove platform: linux/amd64 for native ARM64 on Apple Silicon"
```

---

## Task 2: Build Felix MCP Server — Thin Wrappers

Build the MCP server with all the straightforward wrapper tools first. `felix_read_section` (the compound tool) is in the next task.

**Files:**
- Create: `mcp-server/server.py`
- Create: `mcp-server/requirements.txt`

- [ ] **Step 1: Create requirements.txt**

Create `mcp-server/requirements.txt`:

```
mcp>=1.26.0
httpx>=0.27.0
```

- [ ] **Step 2: Create server.py with thin wrapper tools**

Create `mcp-server/server.py` with these tools wrapping Felix's REST API:

```python
"""Felix MCP Server — document intelligence tools for LLM agents.

Wraps Felix's REST API as MCP tools so any MCP-capable agent
(Claude Code, Codex, etc.) can query processed documents.
"""

import json
import os
from typing import Optional

import httpx
from mcp.server.fastmcp import FastMCP

FELIX_API_URL = os.getenv("FELIX_API_URL", "http://localhost:8001")

mcp = FastMCP(
    "felix",
    instructions=(
        "Felix is a document intelligence platform. Use these tools to explore "
        "documents that have been processed by Felix. Start with "
        "felix_list_documents to see what's available, then use "
        "felix_document_structure to understand the document's organization, "
        "and felix_read_section to read specific sections in full with tables, "
        "images, and footnotes preserved in reading order."
    ),
)


def _api(path: str) -> str:
    return f"{FELIX_API_URL}{path}"


async def _get(path: str, params: dict | None = None) -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(_api(path), params=params)
        resp.raise_for_status()
        return resp.json()


async def _post(path: str, json_body: dict) -> dict:
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(_api(path), json=json_body)
        resp.raise_for_status()
        return resp.json()


@mcp.tool()
async def felix_list_documents() -> str:
    """List all documents that have been ingested by Felix.

    Returns document IDs, file paths, and ingestion timestamps.
    Use this first to discover what's available before querying.
    """
    data = await _get("/documents")
    docs = data.get("documents", [])
    if not docs:
        return "No documents have been ingested yet."
    lines = []
    for d in docs:
        lines.append(
            f"- **ID {d['id']}**: `{d['path']}` "
            f"(ingested {d.get('ingested_at', 'unknown')})"
        )
    return f"Found {len(docs)} document(s):\n" + "\n".join(lines)


@mcp.tool()
async def felix_document_detail(document_id: int) -> str:
    """Get detailed metadata for a document — page count, chunk count,
    table/image counts, and element statistics.

    Args:
        document_id: The document ID (from felix_list_documents)
    """
    data = await _get(f"/documents/{document_id}/detail")
    doc = data["document"]
    summary = (
        f"**{doc['path']}**\n"
        f"- Pages: {len(data['pages'])}\n"
        f"- Chunks: {len(data['chunks'])}\n"
        f"- Tables: {len(data['tables'])}\n"
        f"- Images: {len(data['images'])}\n"
        f"- Layout elements: {len(data['layout_elements'])}\n"
        f"- SHA256: {doc['sha256'][:16]}...\n"
        f"- Ingested: {doc['ingested_at']}"
    )
    return summary


@mcp.tool()
async def felix_document_structure(document_id: int) -> str:
    """Get the document's heading structure (table of contents).

    Returns all section headings with their level, page number, and
    reading order. Use this to understand the document's organization
    before reading specific sections.

    Args:
        document_id: The document ID
    """
    headings = await _get(f"/documents/{document_id}/structure")
    if not headings:
        return "No heading structure found for this document."
    lines = []
    for h in headings:
        indent = "  " * ((h.get("heading_level") or 1) - 1)
        page = f" (p.{h['page_number']})" if h.get("page_number") else ""
        lines.append(f"{indent}- {h.get('heading_text', '(untitled)')}{page}")
    return f"Document structure ({len(headings)} headings):\n" + "\n".join(lines)


@mcp.tool()
async def felix_search(
    query: str,
    top_k: int = 5,
    document_ids: Optional[list[int]] = None,
    search_mode: str = "hybrid",
) -> str:
    """Semantic search across all documents (or specific ones).

    Returns the most relevant chunks with similarity scores,
    headings context, and source locations.

    Args:
        query: Natural language search query
        top_k: Number of results (1-50, default 5)
        document_ids: Optional list of document IDs to search within
        search_mode: "vector", "keyword", or "hybrid" (default "hybrid")
    """
    body = {
        "query": query,
        "top_k": top_k,
        "search_mode": search_mode,
        "include_images": True,
        "include_tables": True,
    }
    if document_ids:
        body["document_ids"] = document_ids
    data = await _post("/search", body)
    results = data.get("results", [])
    if not results:
        return f"No results found for: {query}"
    lines = []
    for r in results:
        headings = " > ".join(r.get("headings") or []) or "(no heading)"
        lines.append(
            f"### Chunk {r['chunk_id']} (similarity: {r['similarity']})\n"
            f"**Source:** {r['document_path']} | **Section:** {headings}\n\n"
            f"{r['content'][:1000]}"
        )
        if r.get("tables"):
            for t in r["tables"]:
                lines.append(f"\n**Table (p.{t.get('page_number')}):**\n{t['content_markdown']}")
        if r.get("images"):
            for img in r["images"]:
                cap = img.get("caption") or "no caption"
                lines.append(f"\n**Image** (p.{img.get('page_number')}): {cap}")
    return f"Found {len(results)} results for \"{query}\":\n\n" + "\n\n---\n\n".join(lines)


@mcp.tool()
async def felix_get_chunk(chunk_id: int) -> str:
    """Get a single chunk's full content with metadata.

    Args:
        chunk_id: The chunk ID (from search results or document chunks)
    """
    data = await _get(f"/chunks/{chunk_id}")
    headings = " > ".join(data.get("headings") or []) or "(no heading)"
    return (
        f"**Chunk {data['chunk_id']}** (index: {data['chunk_index']})\n"
        f"**Document:** {data['document_path']}\n"
        f"**Section:** {headings}\n"
        f"**Tokens:** {data.get('token_count', '?')}\n\n"
        f"{data['content']}"
    )


@mcp.tool()
async def felix_get_tables(document_id: Optional[int] = None) -> str:
    """List tables, optionally filtered by document.

    Returns table metadata including page number, dimensions,
    caption, and markdown content.

    Args:
        document_id: Optional document ID to filter by
    """
    params = {}
    if document_id is not None:
        params["document_id"] = document_id
    data = await _get("/tables", params=params)
    tables = data.get("tables", [])
    if not tables:
        return "No tables found."
    lines = []
    for t in tables:
        cap = t.get("caption") or "no caption"
        lines.append(
            f"### Table {t['id']} (p.{t.get('page_number')}, "
            f"{t['num_rows']}x{t['num_cols']})\n"
            f"**Caption:** {cap}\n\n"
            f"{t.get('content_markdown', '(no content)')}"
        )
    return f"Found {len(tables)} table(s):\n\n" + "\n\n---\n\n".join(lines)


@mcp.tool()
async def felix_get_images(document_id: Optional[int] = None) -> str:
    """List images, optionally filtered by document.

    Returns image metadata including page number, dimensions, and caption.

    Args:
        document_id: Optional document ID to filter by
    """
    params = {}
    if document_id is not None:
        params["document_id"] = document_id
    data = await _get("/images", params=params)
    images = data.get("images", [])
    if not images:
        return "No images found."
    lines = []
    for img in images:
        cap = img.get("caption") or "no caption"
        dims = f"{img.get('width', '?')}x{img.get('height', '?')}"
        lines.append(
            f"- **Image {img['id']}** (p.{img.get('page_number')}, {dims}): {cap}"
        )
    return f"Found {len(images)} image(s):\n" + "\n".join(lines)


@mcp.tool()
async def felix_upload(file_path: str, index_slug: str = "default") -> str:
    """Upload a document to Felix for ingestion.

    The document will be queued for processing. Use felix_ingestion_status
    to monitor progress.

    Args:
        file_path: Absolute path to the file on disk
        index_slug: Index to ingest into (default: "default")
    """
    import os.path

    if not os.path.isfile(file_path):
        return f"Error: File not found: {file_path}"
    filename = os.path.basename(file_path)
    async with httpx.AsyncClient(timeout=60) as client:
        with open(file_path, "rb") as f:
            resp = await client.post(
                _api("/upload"),
                files={"file": (filename, f)},
                data={"index_slug": index_slug},
            )
        resp.raise_for_status()
        data = resp.json()
    return f"Upload result: {data.get('status')} — {data.get('message', '')}"


@mcp.tool()
async def felix_ingestion_status() -> str:
    """Check the status of all ingestion jobs.

    Returns active and recently completed jobs with their progress.
    """
    data = await _get("/ingestion/status")
    jobs = data.get("jobs", [])
    if not jobs:
        return "No active or recent ingestion jobs."
    lines = []
    for j in jobs:
        progress = j.get("progress") or {}
        step = progress.get("step", j.get("status", "unknown"))
        lines.append(
            f"- **{j['filename']}** [{j['status']}] — {step}"
        )
    return "\n".join(lines)
```

- [ ] **Step 3: Install dependencies and verify server starts**

Run:
```bash
cd /Users/datagobes/Projects/felix/mcp-server
uv venv && source .venv/bin/activate
uv pip install -r requirements.txt
python -c "from server import mcp; print('Server module loads OK')"
```

Expected: `Server module loads OK`

- [ ] **Step 4: Commit**

```bash
git add mcp-server/server.py mcp-server/requirements.txt
git commit -m "feat: add Felix MCP server with document query tools"
```

---

## Task 3: Build `felix_read_section` — Compound Tool

The key tool that reconstructs a document section with all elements in reading order. This is server-side composition of multiple Felix API calls.

**Files:**
- Modify: `mcp-server/server.py` (add `felix_read_section` tool)

- [ ] **Step 1: Add `felix_read_section` tool to server.py**

Add the following tool after the existing tools in `server.py`:

```python
@mcp.tool()
async def felix_read_section(
    document_id: int,
    heading: Optional[str] = None,
    start_page: Optional[int] = None,
    end_page: Optional[int] = None,
    include_tables: bool = True,
    include_images: bool = True,
) -> str:
    """Read a document section with full structural fidelity.

    Returns all elements (text, tables, images, footnotes) in reading order,
    exactly as they appear in the original document. This is the primary tool
    for understanding document content — it preserves structure that raw text
    extraction destroys.

    Specify EITHER a heading (finds the section from that heading to the next
    heading of equal or higher level) OR a page range. If neither is given,
    returns the first page.

    Args:
        document_id: The document ID
        heading: Heading text to match (case-insensitive substring match)
        start_page: Start page number (alternative to heading)
        end_page: End page number (alternative to heading)
        include_tables: Include table content as markdown (default True)
        include_images: Include image references with captions (default True)
    """
    # Determine page range from heading or explicit pages
    if heading:
        structure = await _get(f"/documents/{document_id}/structure")
        match = None
        match_idx = None
        heading_lower = heading.lower()
        for i, h in enumerate(structure):
            if heading_lower in (h.get("heading_text") or "").lower():
                match = h
                match_idx = i
                break
        if not match:
            return f"Heading '{heading}' not found. Use felix_document_structure to see available headings."

        s_page = match.get("page_number") or 1
        # Find end: next heading at same or higher (lower number) level
        match_level = match.get("heading_level") or 1
        e_page = None
        for h in structure[match_idx + 1:]:
            h_level = h.get("heading_level") or 1
            if h_level <= match_level:
                e_page = (h.get("page_number") or s_page) - 1
                break
        if e_page is None:
            # Last section — read to end of document
            pages_data = await _get(f"/documents/{document_id}/pages")
            if pages_data:
                e_page = max(p["page_number"] for p in pages_data)
            else:
                e_page = s_page
        start_page = s_page
        end_page = max(e_page, s_page)
    elif start_page is None:
        start_page = 1
        end_page = end_page or 1

    if end_page is None:
        end_page = start_page

    # Fetch elements in the page range with full text
    elements = await _get(
        "/elements/search",
        params={
            "document_id": document_id,
            "page_from": start_page,
            "page_to": end_page,
            "include_text": True,
            "limit": 1000,
        },
    )

    # Fetch tables and images for the page range if requested
    tables_by_page = {}
    if include_tables:
        tables_data = await _get("/tables", params={"document_id": document_id})
        for t in tables_data.get("tables", []):
            pg = t.get("page_number")
            if pg and start_page <= pg <= end_page:
                tables_by_page.setdefault(pg, []).append(t)

    images_by_page = {}
    if include_images:
        images_data = await _get("/images", params={"document_id": document_id})
        for img in images_data.get("images", []):
            pg = img.get("page_number")
            if pg and start_page <= pg <= end_page:
                images_by_page.setdefault(pg, []).append(img)

    # Assemble output in reading order
    output_parts = []
    if heading:
        output_parts.append(f"# Section: {match.get('heading_text', heading)}")
        output_parts.append(f"*Pages {start_page}–{end_page}*\n")

    table_ids_rendered = set()
    image_ids_rendered = set()

    for el in elements:
        etype = el.get("element_type", "")
        text = el.get("full_text") or el.get("text_preview") or ""
        page = el.get("page_number")

        if etype == "section_header":
            level = el.get("heading_level") or 1
            prefix = "#" * (level + 1)  # +1 because section title is #
            output_parts.append(f"\n{prefix} {text}")

        elif etype == "table":
            # Find and render the matching table
            for t in tables_by_page.get(page, []):
                if t["id"] not in table_ids_rendered:
                    cap = t.get("caption") or ""
                    md = t.get("content_markdown") or "(table content unavailable)"
                    output_parts.append(
                        f"\n**Table** (p.{page}){': ' + cap if cap else ''}\n\n{md}"
                    )
                    table_ids_rendered.add(t["id"])
                    break

        elif etype == "picture":
            for img in images_by_page.get(page, []):
                if img["id"] not in image_ids_rendered:
                    cap = img.get("caption") or "no caption"
                    output_parts.append(
                        f"\n**[Image {img['id']}]** (p.{page}): {cap}"
                    )
                    image_ids_rendered.add(img["id"])
                    break

        elif etype in ("caption", "footnote", "page_header", "page_footer"):
            if text.strip():
                output_parts.append(f"\n*[{etype}]* {text}")

        elif etype == "formula":
            output_parts.append(f"\n$$\n{text}\n$$")

        elif etype == "code":
            lang = (el.get("metadata") or {}).get("code_language", "")
            output_parts.append(f"\n```{lang}\n{text}\n```")

        elif etype == "list_item":
            output_parts.append(f"- {text}")

        else:
            # Regular text paragraphs and other elements
            if text.strip():
                output_parts.append(f"\n{text}")

    if not output_parts:
        return f"No content found for pages {start_page}–{end_page}."

    return "\n".join(output_parts)
```

- [ ] **Step 2: Verify server still loads**

Run:
```bash
cd /Users/datagobes/Projects/felix/mcp-server
python -c "from server import mcp; print(f'Tools: {len(mcp._tool_manager._tools)}'); print('OK')"
```

Expected: `Tools: 10` and `OK`

- [ ] **Step 3: Commit**

```bash
git add mcp-server/server.py
git commit -m "feat: add felix_read_section compound tool for structural document reading"
```

---

## Task 4: Register MCP Server in Claude Code

Configure the Felix MCP server so Claude Code can use it as a tool provider.

**Files:**
- Create or modify: `.claude/settings.json` (project-level MCP config)

- [ ] **Step 1: Create project-level MCP config**

Create `.claude/settings.json` with the Felix MCP server. Use `uv run` so dependencies are resolved automatically:

```json
{
  "mcpServers": {
    "felix": {
      "command": "uv",
      "args": [
        "run",
        "--directory", "/Users/datagobes/Projects/felix/mcp-server",
        "--with", "mcp>=1.26.0",
        "--with", "httpx>=0.27.0",
        "mcp", "run", "/Users/datagobes/Projects/felix/mcp-server/server.py"
      ],
      "env": {
        "FELIX_API_URL": "http://localhost:8001"
      }
    }
  }
}
```

Note: This merges with the existing `.claude/settings.local.json` (which has permissions). The project `settings.json` handles MCP servers.

- [ ] **Step 2: Verify the server is recognized**

Restart Claude Code in the felix project directory. Run `/mcp` to check that the `felix` server appears with its tools listed.

- [ ] **Step 3: Commit**

```bash
git add .claude/settings.json
git commit -m "feat: register Felix MCP server in Claude Code config"
```

---

## Task 5: Scaffold Wiki Structure + Schema

Create the llm-wiki directory structure and the CLAUDE.md schema that instructs the agent how to build the wiki using Felix tools.

**Files:**
- Create: `llm-wiki/CLAUDE.md`
- Create: `llm-wiki/wiki/index.md`
- Create: `llm-wiki/wiki/log.md`
- Create: `llm-wiki/raw/README.md`

- [ ] **Step 1: Create wiki directory structure**

```bash
mkdir -p /Users/datagobes/Projects/felix/llm-wiki/wiki/{sources,entities,concepts,chapters}
mkdir -p /Users/datagobes/Projects/felix/llm-wiki/raw
```

- [ ] **Step 2: Create CLAUDE.md schema**

Create `llm-wiki/CLAUDE.md`:

```markdown
# LLM-Wiki Schema — Felix-Powered Knowledge Base

This wiki is built and maintained by an LLM agent using Felix, a document
intelligence platform. The agent never reads raw documents directly — it
queries Felix's structured API for content with full reading order, tables,
images, and cross-references preserved.

## Felix Connection

You have access to Felix via MCP tools (prefixed `felix_`). All source
documents live in Felix. Use Felix tools for all document access.

## Directory Structure

```
wiki/
├── index.md          # Content catalog — read this first
├── log.md            # Chronological operation log
├── overview.md       # High-level synthesis across all sources
├── sources/          # One page per source document
├── entities/         # One page per significant entity
├── concepts/         # One page per major theme or concept
└── chapters/         # Chapter-by-chapter breakdowns
```

## Workflows

### Ingest a New Source

1. `felix_list_documents` — find the document
2. `felix_document_detail` — get metadata and stats
3. `felix_document_structure` — get the full table of contents
4. `felix_read_section` — read each major section in order
5. Write `wiki/sources/<name>.md` — source summary page
6. Create/update entity pages in `wiki/entities/` for every significant entity
7. Create/update concept pages in `wiki/concepts/` for major themes
8. Write chapter summaries in `wiki/chapters/`
9. Update `wiki/index.md` — add entries for all new pages
10. Append to `wiki/log.md` — record what was done

### Query the Wiki

1. Read `wiki/index.md` to find relevant pages
2. If wiki pages are sufficient — synthesize answer from wiki content
3. If more detail needed — use `felix_search` for semantic search
4. If the answer is valuable — file it as a new wiki page

## Page Conventions

Every wiki page starts with YAML frontmatter:

```yaml
---
title: Page Title
type: entity | concept | chapter | source | analysis
sources: [source-name]
felix_refs: [chunk:42, chunk:89, table:7]
last_updated: YYYY-MM-DD
---
```

### Cross-References
- Link to other wiki pages: `[[page-name]]`
- Cite Felix sources: `[Felix:chunk:42]` for traceable claims
- Every factual claim should cite at least one Felix reference

### Writing Style
- Concise and factual
- Use headings to structure content
- Include relevant quotes from the source (cited with Felix refs)
- Note connections to other entities/concepts with wiki links
- Flag contradictions or uncertainties explicitly

## Maintenance

Periodically lint the wiki:
- Check for orphan pages (no inbound links)
- Check for stale claims superseded by newer sources
- Check for missing cross-references
- Check for concepts mentioned but lacking their own page
```

- [ ] **Step 3: Create initial index.md**

Create `llm-wiki/wiki/index.md`:

```markdown
---
title: Index
type: index
last_updated: 2026-04-15
---

# Wiki Index

## Sources
*(No sources ingested yet)*

## Entities
*(No entities yet)*

## Concepts
*(No concepts yet)*

## Chapters
*(No chapters yet)*
```

- [ ] **Step 4: Create initial log.md**

Create `llm-wiki/wiki/log.md`:

```markdown
# Wiki Log

Chronological record of wiki operations.

## [2026-04-15] init | Wiki created

Wiki scaffolded with Felix MCP integration. Ready for first source ingest.
```

- [ ] **Step 5: Create raw/README.md**

Create `llm-wiki/raw/README.md`:

```markdown
# Raw Sources

This wiki's sources are managed by **Felix**, a document intelligence platform.

Felix handles document conversion (via Docling), chunking, embedding, and
structured storage. The wiki layer focuses on synthesis and cross-referencing.

To see available sources, use:
```
felix_list_documents
```

To check ingestion status:
```
felix_ingestion_status
```
```

- [ ] **Step 6: Commit**

```bash
git add llm-wiki/
git commit -m "feat: scaffold llm-wiki with Felix-powered CLAUDE.md schema"
```

---

## Task 6: Start Felix and Ingest the Mythos PDF

Bring up the full Felix stack and process the Mythos PDF.

**Files:**
- No code changes — operational task

- [ ] **Step 1: Start Felix**

```bash
cd /Users/datagobes/Projects/felix
docker compose up -d
```

Wait for all services to be healthy:
```bash
docker compose ps
```

Expected: `felix-postgres`, `felix-api`, `felix-ingestion`, `felix-frontend` all running.

- [ ] **Step 2: Verify API is healthy**

```bash
curl -s http://localhost:8001/health | python3 -m json.tool
```

Expected: `{"status": "ok", ...}`

- [ ] **Step 3: Upload the Mythos PDF**

Either via the Felix UI at http://localhost:5180 (drag-and-drop upload), or via curl:

```bash
curl -X POST http://localhost:8001/upload \
  -F "file=@/path/to/mythos.pdf" \
  -F "index_slug=default"
```

Expected: `{"status": "queued", "message": "File queued for ingestion..."}`

- [ ] **Step 4: Monitor ingestion**

```bash
watch -n 5 'curl -s http://localhost:8001/ingestion/status | python3 -m json.tool'
```

Wait until status shows `complete`. For a 245-page PDF on CPU, expect 5-15 minutes.

- [ ] **Step 5: Verify document is searchable**

```bash
curl -s -X POST http://localhost:8001/search \
  -H "Content-Type: application/json" \
  -d '{"query": "Zeus", "top_k": 3}' | python3 -m json.tool
```

Expected: Results with content about Zeus from the Mythos book.

---

## Task 7: Build the Wiki with Felix MCP Tools

Use Claude Code with the Felix MCP server to build 5-10 wiki pages from the Mythos book. This is the demo — the agent uses Felix tools to read the document and build the wiki.

**Files:**
- Create: `llm-wiki/wiki/overview.md`
- Create: `llm-wiki/wiki/sources/mythos.md`
- Create: `llm-wiki/wiki/chapters/*.md` (2-3 chapters)
- Create: `llm-wiki/wiki/entities/*.md` (2-3 entities)
- Create: `llm-wiki/wiki/concepts/*.md` (1 concept page)
- Modify: `llm-wiki/wiki/index.md`
- Modify: `llm-wiki/wiki/log.md`

- [ ] **Step 1: Start a new Claude Code session in the llm-wiki directory**

```bash
cd /Users/datagobes/Projects/felix/llm-wiki
claude
```

The Felix MCP server should be available. Verify with `/mcp`.

- [ ] **Step 2: Instruct the agent to ingest the Mythos book**

Prompt the agent:

> Ingest the Mythos book that's in Felix. Follow the ingest workflow in CLAUDE.md.
> Start by listing documents, then read the structure. Build out the wiki with:
> - A source summary page
> - An overview page
> - 2-3 chapter pages that best showcase Felix's structural extraction
>   (pick chapters with tables, images, or rich formatting)
> - 2-3 entity pages (major gods/titans) with cross-references
> - 1 concept page that synthesizes a theme across chapters
> Update the index and log when done.

- [ ] **Step 3: Review and commit the generated wiki**

Review the generated pages for quality and Felix citations. Then:

```bash
cd /Users/datagobes/Projects/felix
git add llm-wiki/wiki/
git commit -m "feat: build Mythos wiki using Felix MCP tools"
```

---

## Task 8: Create MCP Server README

Add documentation for how to set up and use the Felix MCP server.

**Files:**
- Create: `mcp-server/README.md`

- [ ] **Step 1: Create README.md**

Create `mcp-server/README.md`:

```markdown
# Felix MCP Server

MCP (Model Context Protocol) server that exposes Felix's document intelligence
API as tools for LLM agents. Enables agents to query processed documents with
full structural fidelity — reading order, tables, images, and cross-references
are preserved.

## Setup

### Prerequisites

- Felix running at `http://localhost:8001` (see root `docker-compose.yml`)
- Python 3.11+ with `uv`

### Claude Code

Add to your project's `.claude/settings.json`:

```json
{
  "mcpServers": {
    "felix": {
      "command": "uv",
      "args": [
        "run",
        "--directory", "/path/to/felix/mcp-server",
        "--with", "mcp>=1.26.0",
        "--with", "httpx>=0.27.0",
        "mcp", "run", "/path/to/felix/mcp-server/server.py"
      ],
      "env": {
        "FELIX_API_URL": "http://localhost:8001"
      }
    }
  }
}
```

### Other MCP Clients

Run the server directly:

```bash
cd mcp-server
uv run --with mcp --with httpx mcp run server.py
```

## Tools

| Tool | Description |
|------|-------------|
| `felix_list_documents` | List all ingested documents |
| `felix_document_detail` | Document metadata and stats |
| `felix_document_structure` | Heading tree (table of contents) |
| `felix_read_section` | Read a section with full structure preserved |
| `felix_search` | Semantic/keyword/hybrid search |
| `felix_get_chunk` | Single chunk with full content |
| `felix_get_tables` | List tables with markdown content |
| `felix_get_images` | List images with captions |
| `felix_upload` | Upload a document for ingestion |
| `felix_ingestion_status` | Check ingestion progress |

### Key Tool: `felix_read_section`

The primary tool for document reading. Returns all elements in reading order:
text paragraphs, section headers, tables (as markdown), image references,
footnotes, code blocks, and formulas — exactly as structured in the original
document.

```
felix_read_section(document_id=1, heading="Chapter 3")
```

This reconstructs the section faithfully, which is what raw PDF-to-text
extraction fails to do.

## Configuration

| Env Variable | Default | Description |
|---|---|---|
| `FELIX_API_URL` | `http://localhost:8001` | Felix API base URL |
```

- [ ] **Step 2: Commit**

```bash
git add mcp-server/README.md
git commit -m "docs: add Felix MCP server README with setup instructions"
```

---

## Summary

| Task | What it produces | Estimated effort |
|------|-----------------|-----------------|
| 1. Fix Docker Compose for ARM | Native ARM64 containers | 2 min |
| 2. MCP Server — thin wrappers | 9 working tools | 5 min |
| 3. MCP Server — `felix_read_section` | The key compound tool | 5 min |
| 4. Register in Claude Code | MCP config | 2 min |
| 5. Scaffold wiki | Directory structure + CLAUDE.md schema | 3 min |
| 6. Start Felix + ingest | Running stack + processed Mythos PDF | 15 min (mostly waiting) |
| 7. Build the wiki | 5-10 wiki pages with Felix citations | 15 min |
| 8. MCP Server README | Documentation | 3 min |

Tasks 1-5 can be done immediately. Task 6 requires the Mythos PDF. Task 7 requires Felix running with the PDF ingested. Task 8 can be done anytime.

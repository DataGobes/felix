# Felix MCP Server

MCP server that exposes Felix's document intelligence API as tools for LLM agents. Enables agents to query processed documents with full structural fidelity — reading order, tables, images, and cross-references preserved.

## Setup

### Prerequisites

- Felix running at `http://localhost:8001` (see root `docker-compose.yml`)
- Python 3.11+ with `uv`

### Claude Code

The project `.claude/settings.json` already registers this server. Just restart Claude Code in the felix directory.

To configure manually, add to your `.claude/settings.json`:

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

The primary tool for document reading. Returns all elements in reading order: text paragraphs, section headers, tables (as markdown), image references, footnotes, code blocks, and formulas — exactly as structured in the original document.

```
felix_read_section(document_id=1, heading="Chapter 3")
```

This reconstructs the section faithfully, which is what raw PDF-to-text extraction fails to do.

## Configuration

| Env Variable | Default | Description |
|---|---|---|
| `FELIX_API_URL` | `http://localhost:8001` | Felix API base URL |

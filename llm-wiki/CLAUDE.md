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

# Felix Native Autonomous LLM-Wiki — Design

**Date:** 2026-06-13
**Status:** Approved (design); implementation pending
**Builds on:** [`2026-04-15-felix-mcp-llm-wiki-design.md`](2026-04-15-felix-mcp-llm-wiki-design.md)

## Goal

Promote the manual Mythos-wiki ritual into a first-class Felix capability. Today an
*external* Claude agent connects via MCP and follows hand-written instructions in
`llm-wiki/CLAUDE.md` to build a wiki. This feature makes Felix build the wiki
**itself**: select an index → Felix autonomously produces a structured, interlinked,
cited wiki, backed by a lightweight entity–relationship graph, viewable in the frontend.

## Context

Karpathy's llm-wiki (April 2026) describes LLMs incrementally building a persistent,
interlinked markdown wiki that sits between the user and raw sources — a "compounding
artifact." Felix already realizes this pattern manually (commit `c269a06`, the 10-page
Mythos wiki). The wiki's entity/concept pages and `[[links]]` are, structurally, a
knowledge graph — so a lightweight GraphRAG pass is not a separate feature but the
mechanism that decides *which pages exist* and *how they cross-link*.

This is the **"reason" layer**, sitting beside the existing layers:

```
read  → ingestion.py   (Docling → chunks → pgvector)
retrieve → search.py   (semantic/hybrid search, chat)
reason → wiki builder  (NEW: index → entity graph → wiki pages)
```

## Locked Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Autonomy | **Self-contained backend agent** | Felix builds wikis on its own; no external Claude Code required. |
| Storage | **DB-backed + frontend viewer** | Fits Felix's Postgres + React architecture; queryable, navigable, graph-renderable. |
| GraphRAG | **Lightweight entity-graph** | Entity/relationship extraction drives page set + cross-links; high value, natural fit. Full Microsoft GraphRAG (Leiden communities, hierarchical summaries) deferred. |
| Builder LLM | **MiniMax M2 (existing client)** | Reuse `search.py`'s `AsyncOpenAI` client + `MINIMAX_API_KEY` (sk-api app key). No new dependency. Embeddings stay Azure OpenAI. |
| Orchestration | **Deterministic 4-stage pipeline + job state-machine** | Mirrors the proven `ingestion_jobs` pattern: resumable, testable, real-time progress, won't wander or over-spend. |

## Architecture

A new `felix-wiki` worker runs a fixed 4-stage pipeline. Each stage advances a
`wiki_jobs` row through statuses, emitting progress over SSE exactly as ingestion does.
The builder consumes Felix's own search/structure capabilities (in-process service
functions, not HTTP round-trips through MCP) and the MiniMax client for reasoning.

### Pipeline stages

**Stage 1 — Extract (graph pass).** For each document in the index:
walk `document_structure` → `read_section` per major section → LLM extracts
**entities** (name, type, description) and **relationships** (subject, predicate,
object), each cited to the chunks they came from. Persist to `wiki_entities` /
`wiki_relationships` / `entity_chunks`. After all docs, **dedup/merge** entities across
documents by normalized name + embedding cosine similarity above a threshold.

**Stage 2 — Plan.** From the merged graph, compute the page set:
- one **source** page per document,
- **entity** pages for *significant* entities (see `score_entity` below),
- **concept** pages for clusters of related entities/themes,
- **chapter** pages from document structure,
- one **overview** page.
Relationships become planned `[[cross-links]]` between the resulting pages.

> **Open implementation choice (`score_entity`).** What makes an entity "worthy" of its
> own page — raw mention count, graph degree centrality, or a hybrid? This is a
> precision-vs-bloat tradeoff and is intentionally left as a focused decision point at
> implementation time. The planner calls a single `score_entity(entity, graph) -> float`
> with a configurable threshold.

**Stage 3 — Write.** Per planned page (parallelizable): gather relevant chunks via the
entity→chunk map plus `felix_search`, then the LLM writes markdown with YAML
frontmatter, `[[links]]`, and `[Felix:chunk:N]` citations on every factual claim.
Persist to `wiki_pages`; record outbound links in `wiki_links`.

**Stage 4 — Assemble & Lint.** Generate `index.md` (catalog) and `log.md`
(chronological). Run the lint pass: orphan pages (no inbound links), missing
cross-references, concepts mentioned without a page, and contradictions. Apply
mechanical fixes; flag semantic ones in the log.

## Data Model

All tables scoped by `index_id` (FK → `indexes`), cascade-deleted with the index.

| Table | Key columns | Purpose |
|-------|-------------|---------|
| `wiki_jobs` | id, index_id, status (`queued/extracting/planning/writing/linting/completed/failed`), progress JSONB, error_message, created_at, started_at, updated_at, completed_at | Job state-machine; mirrors `ingestion_jobs`. |
| `wiki_entities` | id, index_id, name, normalized_name, type, description, embedding VECTOR(1536), mention_count, metadata | Graph nodes. |
| `wiki_relationships` | id, index_id, subject_entity_id, predicate, object_entity_id, description, chunk_refs[] | Graph edges. |
| `entity_chunks` | entity_id, chunk_id | Provenance: which chunks mention an entity. |
| `wiki_pages` | id, index_id, slug, title, type (`source/entity/concept/chapter/overview/index/log`), content_md, frontmatter JSONB, felix_refs[], entity_id (nullable), created_at, updated_at | Wiki pages. UNIQUE(index_id, slug). |
| `wiki_links` | id, source_page_id, target_page_id (nullable), target_slug, link_type | Resolved + pending cross-links; powers graph view + orphan/lint detection. |

Reuses existing `chunks` (citations), `embeddings` (entity-chunk relevance), and
`indexes` (scoping).

## API (added to `search.py`)

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/indexes/{slug}/wiki/build` | Enqueue a build (`mode=full` for v1). Returns `wiki_jobs` row. |
| GET | `/indexes/{slug}/wiki/status` | Latest job status + progress. |
| GET | `/indexes/{slug}/wiki/stream` | SSE progress (reuse ingestion streaming pattern). |
| GET | `/indexes/{slug}/wiki` | Page list / catalog (the `index.md` equivalent). |
| GET | `/indexes/{slug}/wiki/pages/{page_slug}` | Page content + resolved links. |
| GET | `/indexes/{slug}/wiki/graph` | `{nodes, edges}` for the graph view. |
| DELETE | `/indexes/{slug}/wiki` | Clear the wiki for the index. |

## Frontend

New `Wiki.jsx` + route registered in `AppShell.jsx`:
- **Left:** page tree grouped by `type`.
- **Center:** rendered markdown; `[[links]]` are clickable in-wiki navigation;
  `[Felix:chunk:N]` citations open the chunk in the existing `ChunksViewer`.
- **Toggle:** force-directed graph of entities + pages (reuse the existing graph-view
  dependency already in the frontend).
- **Build action:** "Build Wiki" on an index with live progress, reusing the
  `IngestionPipeline.jsx` SSE pattern.

## LLM Usage

MiniMax M2 via `search.py`'s existing `AsyncOpenAI` client (`MINIMAX_API_KEY`,
`base_url=https://api.minimaxi.chat/v1`, `CHAT_MODEL`):
- **Extraction:** structured JSON output, one call per section.
- **Writing:** markdown generation; the system prompt enforces `[Felix:chunk:N]` on
  factual claims and `[[links]]` for cross-references.
- **Lint:** a review pass over the assembled wiki.

Azure OpenAI embeddings (existing) are reused for entity dedup and entity-chunk
relevance ranking. No new model dependency is introduced.

## Provenance & Citation

The Mythos discipline is preserved and made mechanical: every factual claim cites
`[Felix:chunk:N]`; frontmatter carries `felix_refs` and `sources`; `[[links]]` persist
as `wiki_links` rows. This keeps Karpathy's "traceable, compounding artifact" property
and lets lint operate as SQL/graph queries rather than prose inspection.

## Incremental Updates

Felix already tracks `sha256` per document. **v1 ships full-rebuild** (clear + rebuild
per index). The schema deliberately supports a later delta path:
detect new/changed docs → extract only deltas → merge into the graph → re-plan affected
pages → rewrite and append to `log.md`.

## Testing

- **Unit (pytest, mirroring `backend/tests`):** entity dedup/merge, `score_entity` +
  page-set planner, link resolver, lint rules.
- **Integration:** a small fixture index run through the full pipeline against a
  **stubbed deterministic LLM** (fixed extraction/writing responses) → assert pages,
  links, citations present, and zero orphans. Stubbing isolates control flow from
  model nondeterminism and avoids token spend in CI.
- **Frontend:** component test for `Wiki.jsx` link navigation (`[[link]]` → page,
  `[Felix:chunk]` → ChunksViewer).

## Build Phasing

1. **Schema + extract:** new tables + migration; `wiki_jobs`; Stage 1 extraction with entity dedup.
2. **Plan + write:** Stage 2 planner (`score_entity`) + Stage 3 page writing; pages persisted.
3. **API + lint + assemble:** Stage 4; all endpoints; SSE progress.
4. **Frontend:** `Wiki.jsx` viewer + graph + build action.

Each phase is independently testable and shippable behind the others.

## Out of Scope (v1)

- Full Microsoft GraphRAG (Leiden community detection, hierarchical community summaries,
  global/local query modes).
- Incremental/delta rebuilds (schema-ready, not implemented).
- Human-in-the-loop discussion during ingest (Karpathy's original); v1 is fully autonomous.

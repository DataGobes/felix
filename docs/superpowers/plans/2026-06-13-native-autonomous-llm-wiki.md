# Native Autonomous LLM-Wiki Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Felix autonomously build a structured, interlinked, cited wiki from any index — a self-contained backend pipeline (extract → plan → write → lint) driven by MiniMax M2, persisted to Postgres, and surfaced in a React wiki viewer.

**Architecture:** A new `backend/wiki_builder.py` module exposes pure functions (entity dedup, page planning, link extraction, lint) plus a `run_wiki_build` orchestrator launched as an asyncio background task from a new `POST /indexes/{slug}/wiki/build` endpoint. State is tracked in a `wiki_jobs` table mirroring `ingestion_jobs`; the entity graph lives in `wiki_entities`/`wiki_relationships`/`entity_chunks`; output in `wiki_pages`/`wiki_links`. The builder reads chunk text directly from the DB and calls MiniMax via an injected `LLM` wrapper, so unit tests stub the LLM/embeddings for full determinism.

**Tech Stack:** Python 3.11+, FastAPI, asyncpg, openai SDK (Azure embeddings + MiniMax chat), PostgreSQL 16 + pgvector, pytest + pytest-asyncio; React 19 + Vite, react-markdown, custom `useForceLayout`.

**Reference spec:** [`docs/superpowers/specs/2026-06-13-native-autonomous-llm-wiki-design.md`](../specs/2026-06-13-native-autonomous-llm-wiki-design.md)

---

## File Structure

| File | Responsibility | New/Modify |
|------|----------------|------------|
| `backend/init.sql` | Append 6 wiki tables + indexes (idempotent) | Modify |
| `backend/wiki_builder.py` | Dataclasses, pure graph/page/lint functions, `LLM` wrapper, DB persistence, `run_wiki_build` orchestrator | Create |
| `backend/test_wiki_builder.py` | Unit tests for pure functions + stubbed end-to-end pipeline | Create |
| `backend/search.py` | Wiki API endpoints + background-task trigger | Modify |
| `backend/test_wiki_api.py` | Endpoint tests (mocked pool) | Create |
| `frontend/src/api/client.jsx` | Wiki API calls | Modify |
| `frontend/src/hooks/useWikiBuild.js` | SSE build-progress hook (mirrors `useIngestionStatus`) | Create |
| `frontend/src/components/Wiki.jsx` | Wiki viewer (tree + markdown + citations) | Create |
| `frontend/src/AppShell.jsx` | Add "Wiki" nav item | Modify |
| `frontend/src/App.jsx` | Add `/wiki` route | Modify |
| `frontend/src/components/Wiki.test.jsx` | Component test for citation/link navigation | Create |

---

# Phase 1 — Schema + Graph Extraction

## Task 1: Add wiki schema to init.sql

**Files:**
- Modify: `backend/init.sql` (append at end)

- [ ] **Step 1: Append the wiki tables**

Append to the end of `backend/init.sql`:

```sql
-- ============================================================
-- LLM-Wiki: entity graph + generated wiki pages (per index)
-- ============================================================

CREATE TABLE IF NOT EXISTS wiki_jobs (
  id            SERIAL PRIMARY KEY,
  index_id      INTEGER NOT NULL REFERENCES indexes(id) ON DELETE CASCADE,
  status        VARCHAR(50)  NOT NULL DEFAULT 'queued',
  progress      JSONB        NOT NULL DEFAULT '{}',
  error_message TEXT,
  created_at    TIMESTAMP    NOT NULL DEFAULT NOW(),
  started_at    TIMESTAMP,
  updated_at    TIMESTAMP    NOT NULL DEFAULT NOW(),
  completed_at  TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_wiki_jobs_active
  ON wiki_jobs (status) WHERE status NOT IN ('completed', 'failed');

CREATE TABLE IF NOT EXISTS wiki_entities (
  id              SERIAL PRIMARY KEY,
  index_id        INTEGER NOT NULL REFERENCES indexes(id) ON DELETE CASCADE,
  name            TEXT NOT NULL,
  normalized_name TEXT NOT NULL,
  type            VARCHAR(50) NOT NULL DEFAULT 'other',
  description     TEXT,
  embedding       VECTOR(1536),
  mention_count   INTEGER NOT NULL DEFAULT 0,
  metadata        JSONB NOT NULL DEFAULT '{}',
  UNIQUE (index_id, normalized_name)
);

CREATE TABLE IF NOT EXISTS wiki_relationships (
  id                SERIAL PRIMARY KEY,
  index_id          INTEGER NOT NULL REFERENCES indexes(id) ON DELETE CASCADE,
  subject_entity_id INTEGER NOT NULL REFERENCES wiki_entities(id) ON DELETE CASCADE,
  predicate         TEXT NOT NULL,
  object_entity_id  INTEGER NOT NULL REFERENCES wiki_entities(id) ON DELETE CASCADE,
  description       TEXT,
  chunk_refs        INTEGER[] NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS entity_chunks (
  entity_id INTEGER NOT NULL REFERENCES wiki_entities(id) ON DELETE CASCADE,
  chunk_id  INTEGER NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
  PRIMARY KEY (entity_id, chunk_id)
);

CREATE TABLE IF NOT EXISTS wiki_pages (
  id          SERIAL PRIMARY KEY,
  index_id    INTEGER NOT NULL REFERENCES indexes(id) ON DELETE CASCADE,
  slug        VARCHAR(200) NOT NULL,
  title       TEXT NOT NULL,
  type        VARCHAR(50) NOT NULL,
  content_md  TEXT NOT NULL DEFAULT '',
  frontmatter JSONB NOT NULL DEFAULT '{}',
  felix_refs  INTEGER[] NOT NULL DEFAULT '{}',
  entity_id   INTEGER REFERENCES wiki_entities(id) ON DELETE SET NULL,
  created_at  TIMESTAMP NOT NULL DEFAULT NOW(),
  updated_at  TIMESTAMP NOT NULL DEFAULT NOW(),
  UNIQUE (index_id, slug)
);

CREATE TABLE IF NOT EXISTS wiki_links (
  id             SERIAL PRIMARY KEY,
  source_page_id INTEGER NOT NULL REFERENCES wiki_pages(id) ON DELETE CASCADE,
  target_page_id INTEGER REFERENCES wiki_pages(id) ON DELETE CASCADE,
  target_slug    VARCHAR(200) NOT NULL,
  link_type      VARCHAR(50) NOT NULL DEFAULT 'wiki'
);

CREATE INDEX IF NOT EXISTS idx_wiki_pages_index ON wiki_pages(index_id);
CREATE INDEX IF NOT EXISTS idx_wiki_entities_index ON wiki_entities(index_id);
CREATE INDEX IF NOT EXISTS idx_wiki_links_source ON wiki_links(source_page_id);
```

- [ ] **Step 2: Apply schema to the running dev DB**

`init.sql` is mounted at `/docker-entrypoint-initdb.d/init.sql` and is fully idempotent (`IF NOT EXISTS` / guarded `DO` blocks), so re-running it adds the new tables without touching existing data.

Run:
```bash
docker compose exec -T felix-postgres \
  psql -U "${POSTGRES_USER:-felix}" -d "${POSTGRES_DB:-felix}" \
  -f /docker-entrypoint-initdb.d/init.sql
```
Expected: a stream of `CREATE TABLE` / `CREATE INDEX` (or `NOTICE ... already exists, skipping`) with no `ERROR`.

- [ ] **Step 3: Verify the tables exist**

Run:
```bash
docker compose exec -T felix-postgres \
  psql -U "${POSTGRES_USER:-felix}" -d "${POSTGRES_DB:-felix}" \
  -c "\dt wiki_*; \dt entity_chunks"
```
Expected: lists `wiki_jobs`, `wiki_entities`, `wiki_relationships`, `wiki_pages`, `wiki_links`, `entity_chunks`.

- [ ] **Step 4: Commit**

```bash
git add backend/init.sql
git commit -m "feat(wiki): add entity-graph + wiki-page schema"
```

---

## Task 2: Builder dataclasses + JSON parsing helper

**Files:**
- Create: `backend/wiki_builder.py`
- Test: `backend/test_wiki_builder.py`

- [ ] **Step 1: Write the failing test**

Create `backend/test_wiki_builder.py`:

```python
import wiki_builder as wb


def test_extract_json_plain():
    assert wb.extract_json('{"a": 1}') == {"a": 1}


def test_extract_json_fenced():
    text = "Sure!\n```json\n{\"entities\": [], \"relationships\": []}\n```\nDone."
    assert wb.extract_json(text) == {"entities": [], "relationships": []}


def test_extract_json_embedded():
    text = 'noise before {"x": [1, 2]} noise after'
    assert wb.extract_json(text) == {"x": [1, 2]}


def test_extract_json_invalid_returns_empty_dict():
    assert wb.extract_json("not json at all") == {}


def test_slugify():
    assert wb.slugify("Claude Mythos Preview!") == "claude-mythos-preview"
    assert wb.slugify("  Multi   Space ") == "multi-space"
    assert wb.slugify("CamelCase/With:Punct") == "camelcase-with-punct"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest test_wiki_builder.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'wiki_builder'`.

- [ ] **Step 3: Create the module with dataclasses + helpers**

Create `backend/wiki_builder.py`:

```python
"""Felix native LLM-wiki builder.

Pure functions (extraction parsing, dedup, planning, lint) plus a
`run_wiki_build` orchestrator that drives the extract -> plan -> write -> lint
pipeline. The LLM and embedding clients are injected so tests can stub them.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Optional, Protocol


# --------------------------------------------------------------------------
# Data structures
# --------------------------------------------------------------------------

@dataclass
class Entity:
    name: str
    type: str = "other"
    description: str = ""
    chunk_ids: list[int] = field(default_factory=list)


@dataclass
class Relationship:
    subject: str
    predicate: str
    object: str
    description: str = ""
    chunk_ids: list[int] = field(default_factory=list)


@dataclass
class ChunkRow:
    chunk_id: int
    document_id: int
    content: str
    headings: list[str] = field(default_factory=list)


@dataclass
class DocRow:
    document_id: int
    path: str


@dataclass
class PageSpec:
    slug: str
    title: str
    type: str  # source | entity | concept | chapter | overview
    entity_name: Optional[str] = None
    source_document_id: Optional[int] = None
    related_chunk_ids: list[int] = field(default_factory=list)
    links: list[str] = field(default_factory=list)  # target slugs


# --------------------------------------------------------------------------
# Injected client protocols
# --------------------------------------------------------------------------

class LLM(Protocol):
    async def complete(self, system: str, user: str) -> str: ...


class Embedder(Protocol):
    async def embed(self, text: str) -> list[float]: ...


# --------------------------------------------------------------------------
# Pure helpers
# --------------------------------------------------------------------------

def extract_json(text: str) -> dict:
    """Best-effort JSON object extraction from an LLM response.

    Handles plain JSON, ```json fenced blocks, and JSON embedded in prose.
    Returns {} when nothing parseable is found.
    """
    if not text:
        return {}
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    candidate = fence.group(1) if fence else None
    if candidate is None:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            candidate = text[start:end + 1]
    if candidate is None:
        return {}
    try:
        result = json.loads(candidate)
        return result if isinstance(result, dict) else {}
    except json.JSONDecodeError:
        return {}


def slugify(name: str) -> str:
    """Lowercase, hyphenate, strip punctuation -> a stable page slug."""
    s = name.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest test_wiki_builder.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/wiki_builder.py backend/test_wiki_builder.py
git commit -m "feat(wiki): builder dataclasses + json/slug helpers"
```

---

## Task 3: Entity-extraction prompt + response parser

**Files:**
- Modify: `backend/wiki_builder.py`
- Test: `backend/test_wiki_builder.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/test_wiki_builder.py`:

```python
def test_build_extraction_prompt_includes_chunk_markers():
    chunks = [
        wb.ChunkRow(chunk_id=7, document_id=1, content="Claude scored 100% on Cybench."),
        wb.ChunkRow(chunk_id=8, document_id=1, content="The model showed deception."),
    ]
    system, user = wb.build_extraction_prompt(chunks)
    assert "JSON" in system
    assert "[chunk:7]" in user
    assert "[chunk:8]" in user
    assert "Cybench" in user


def test_parse_extraction_assigns_batch_chunk_ids():
    raw = (
        '{"entities": [{"name": "Claude", "type": "system", '
        '"description": "An AI model", "chunk_ids": [7]}], '
        '"relationships": [{"subject": "Claude", "predicate": "scored_on", '
        '"object": "Cybench", "description": "100%", "chunk_ids": [7]}]}'
    )
    batch_ids = [7, 8]
    ents, rels = wb.parse_extraction(raw, batch_ids)
    assert len(ents) == 1
    assert ents[0].name == "Claude"
    assert ents[0].chunk_ids == [7]
    assert len(rels) == 1
    assert rels[0].subject == "Claude" and rels[0].object == "Cybench"


def test_parse_extraction_defaults_chunk_ids_to_batch():
    # When the model omits chunk_ids, fall back to all batch ids.
    raw = '{"entities": [{"name": "Firefox", "type": "system"}], "relationships": []}'
    ents, rels = wb.parse_extraction(raw, [7, 8])
    assert ents[0].chunk_ids == [7, 8]
    assert ents[0].description == ""


def test_parse_extraction_handles_garbage():
    ents, rels = wb.parse_extraction("the model returned prose", [1])
    assert ents == [] and rels == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest test_wiki_builder.py -k extraction -v`
Expected: FAIL — `AttributeError: module 'wiki_builder' has no attribute 'build_extraction_prompt'`.

- [ ] **Step 3: Implement prompt builder + parser**

Append to `backend/wiki_builder.py`:

```python
_EXTRACTION_SYSTEM = """You are an information-extraction engine for a document \
knowledge base. From the supplied text chunks, extract the salient ENTITIES \
(people, organizations, systems, concepts, metrics, events) and the \
RELATIONSHIPS between them.

Respond with ONLY a JSON object, no prose, in this exact shape:
{
  "entities": [
    {"name": "...", "type": "person|organization|system|concept|metric|event|other",
     "description": "one sentence", "chunk_ids": [<int>, ...]}
  ],
  "relationships": [
    {"subject": "<entity name>", "predicate": "<verb phrase>",
     "object": "<entity name>", "description": "one sentence", "chunk_ids": [<int>, ...]}
  ]
}
Use the [chunk:N] markers in the text to populate chunk_ids with the chunks \
that support each item. Prefer canonical entity names. Omit trivial entities."""


def build_extraction_prompt(chunks: list[ChunkRow]) -> tuple[str, str]:
    parts = []
    for c in chunks:
        head = " > ".join(c.headings) if c.headings else ""
        prefix = f"[chunk:{c.chunk_id}]" + (f" ({head})" if head else "")
        parts.append(f"{prefix}\n{c.content}")
    user = "Extract entities and relationships from these chunks:\n\n" + "\n\n".join(parts)
    return _EXTRACTION_SYSTEM, user


def parse_extraction(raw: str, batch_chunk_ids: list[int]) -> tuple[list[Entity], list[Relationship]]:
    data = extract_json(raw)
    entities: list[Entity] = []
    for e in data.get("entities", []) or []:
        name = (e.get("name") or "").strip()
        if not name:
            continue
        cids = [int(x) for x in (e.get("chunk_ids") or []) if isinstance(x, (int, float))]
        entities.append(Entity(
            name=name,
            type=(e.get("type") or "other").strip().lower(),
            description=(e.get("description") or "").strip(),
            chunk_ids=cids or list(batch_chunk_ids),
        ))
    relationships: list[Relationship] = []
    for r in data.get("relationships", []) or []:
        subj = (r.get("subject") or "").strip()
        obj = (r.get("object") or "").strip()
        if not subj or not obj:
            continue
        cids = [int(x) for x in (r.get("chunk_ids") or []) if isinstance(x, (int, float))]
        relationships.append(Relationship(
            subject=subj,
            predicate=(r.get("predicate") or "related_to").strip(),
            object=obj,
            description=(r.get("description") or "").strip(),
            chunk_ids=cids or list(batch_chunk_ids),
        ))
    return entities, relationships
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest test_wiki_builder.py -k extraction -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/wiki_builder.py backend/test_wiki_builder.py
git commit -m "feat(wiki): entity-extraction prompt + response parser"
```

---

## Task 4: Entity dedup / merge

**Files:**
- Modify: `backend/wiki_builder.py`
- Test: `backend/test_wiki_builder.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/test_wiki_builder.py`:

```python
def test_merge_entities_by_name_combines_duplicates():
    ents = [
        wb.Entity(name="Claude", type="system", description="short", chunk_ids=[1]),
        wb.Entity(name="  claude ", type="system", description="a much longer description", chunk_ids=[2, 1]),
        wb.Entity(name="Firefox", type="system", description="browser", chunk_ids=[3]),
    ]
    merged = wb.merge_entities_by_name(ents)
    assert len(merged) == 2
    claude = next(m for m in merged if m.name.lower().strip() == "claude")
    # Longest description wins; chunk_ids deduped + sorted.
    assert claude.description == "a much longer description"
    assert claude.chunk_ids == [1, 2]


def test_normalize_name():
    assert wb.normalize_name("  The  Model ") == "the model"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest test_wiki_builder.py -k "merge or normalize" -v`
Expected: FAIL — no attribute `merge_entities_by_name`.

- [ ] **Step 3: Implement**

Append to `backend/wiki_builder.py`:

```python
def normalize_name(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip().lower())


def merge_entities_by_name(entities: list[Entity]) -> list[Entity]:
    """Merge entities sharing a normalized name. Longest description wins;
    chunk_ids are unioned + sorted; mention frequency preserved via chunk_ids."""
    by_norm: dict[str, Entity] = {}
    for e in entities:
        key = normalize_name(e.name)
        if key not in by_norm:
            by_norm[key] = Entity(name=e.name.strip(), type=e.type,
                                  description=e.description, chunk_ids=list(e.chunk_ids))
            continue
        cur = by_norm[key]
        if len(e.description) > len(cur.description):
            cur.description = e.description
        if e.type != "other" and cur.type == "other":
            cur.type = e.type
        cur.chunk_ids = sorted(set(cur.chunk_ids) | set(e.chunk_ids))
    return list(by_norm.values())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest test_wiki_builder.py -k "merge or normalize" -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/wiki_builder.py backend/test_wiki_builder.py
git commit -m "feat(wiki): entity name-based dedup/merge"
```

---

## Task 5: Embedding-similarity merge pass

**Files:**
- Modify: `backend/wiki_builder.py`
- Test: `backend/test_wiki_builder.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/test_wiki_builder.py`:

```python
import pytest


class StubEmbedder:
    """Returns a fixed vector per entity name for deterministic similarity."""
    def __init__(self, vectors):
        self._vectors = vectors
    async def embed(self, text):
        return self._vectors[text]


def test_cosine():
    assert wb.cosine([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)
    assert wb.cosine([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)


async def test_merge_entities_by_embedding_merges_near_duplicates():
    ents = [
        wb.Entity(name="LLM", description="large language model", chunk_ids=[1]),
        wb.Entity(name="Large Language Model", description="an LLM", chunk_ids=[2]),
        wb.Entity(name="Firefox", description="browser", chunk_ids=[3]),
    ]
    embedder = StubEmbedder({
        "LLM: large language model": [1.0, 0.0, 0.0],
        "Large Language Model: an LLM": [0.99, 0.01, 0.0],
        "Firefox: browser": [0.0, 0.0, 1.0],
    })
    merged = await wb.merge_entities_by_embedding(ents, embedder, threshold=0.9)
    assert len(merged) == 2
    survivor = next(m for m in merged if m.name in ("LLM", "Large Language Model"))
    assert survivor.chunk_ids == [1, 2]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest test_wiki_builder.py -k "cosine or embedding" -v`
Expected: FAIL — no attribute `cosine`.

- [ ] **Step 3: Implement**

Append to `backend/wiki_builder.py`:

```python
import math


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


async def merge_entities_by_embedding(
    entities: list[Entity], embedder: Embedder, threshold: float = 0.88
) -> list[Entity]:
    """Greedy merge of entities whose embeddings exceed `threshold`.
    First occurrence is the survivor; later near-duplicates fold into it."""
    survivors: list[Entity] = []
    vectors: list[list[float]] = []
    for e in entities:
        vec = await embedder.embed(f"{e.name}: {e.description}")
        merged_into = None
        for i, sv in enumerate(vectors):
            if cosine(vec, sv) >= threshold:
                merged_into = i
                break
        if merged_into is None:
            survivors.append(Entity(name=e.name, type=e.type,
                                   description=e.description, chunk_ids=list(e.chunk_ids)))
            vectors.append(vec)
        else:
            tgt = survivors[merged_into]
            if len(e.description) > len(tgt.description):
                tgt.description = e.description
            tgt.chunk_ids = sorted(set(tgt.chunk_ids) | set(e.chunk_ids))
    return survivors
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest test_wiki_builder.py -k "cosine or embedding" -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/wiki_builder.py backend/test_wiki_builder.py
git commit -m "feat(wiki): embedding-similarity entity merge pass"
```

---

# Phase 2 — Planning + Page Writing

## Task 6: `score_entity` + page planner

> **⚠ Learning-mode checkpoint:** `score_entity` encodes the precision-vs-bloat tradeoff
> (which entities earn their own page). The reference implementation below is a working
> default; during execution, pause and invite the user to tune/replace this ~8-line
> heuristic before continuing. The test pins the *contract* (monotonic in mentions and
> degree), not the exact formula, so a user revision that preserves monotonicity passes.

**Files:**
- Modify: `backend/wiki_builder.py`
- Test: `backend/test_wiki_builder.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/test_wiki_builder.py`:

```python
def _deg_map(rels):
    return wb.degree_map(rels)


def test_degree_map_counts_both_directions():
    rels = [
        wb.Relationship(subject="A", predicate="x", object="B"),
        wb.Relationship(subject="B", predicate="y", object="C"),
    ]
    dm = wb.degree_map(rels)
    assert dm["b"] == 2 and dm["a"] == 1 and dm["c"] == 1


def test_score_entity_monotonic():
    e_small = wb.Entity(name="A", chunk_ids=[1])
    e_big = wb.Entity(name="A", chunk_ids=[1, 2, 3, 4])
    deg = {"a": 5}
    assert wb.score_entity(e_big, deg) > wb.score_entity(e_small, deg)
    # More degree -> higher score at equal mentions.
    assert wb.score_entity(e_small, {"a": 9}) > wb.score_entity(e_small, {"a": 0})


def test_plan_pages_produces_expected_set():
    docs = [wb.DocRow(document_id=1, path="card.pdf")]
    ents = [
        wb.Entity(name="Claude", type="system", description="model", chunk_ids=[1, 2, 3]),
        wb.Entity(name="Alignment", type="concept", description="safety", chunk_ids=[1, 2, 3]),
        wb.Entity(name="Trivia", type="other", description="x", chunk_ids=[9]),
    ]
    rels = [wb.Relationship(subject="Claude", predicate="exhibits", object="Alignment", chunk_ids=[1])]
    pages = wb.plan_pages(docs, ents, rels, threshold=2.0)
    types = {p.type for p in pages}
    slugs = {p.slug for p in pages}
    assert "overview" in types
    assert "overview" in slugs
    assert "claude" in slugs            # entity page (high score)
    assert "alignment" in slugs         # concept page (high score)
    assert "trivia" not in slugs        # below threshold -> no page
    # Source page exists for the document.
    assert any(p.type == "source" for p in pages)
    # Relationship became a planned cross-link.
    claude_page = next(p for p in pages if p.slug == "claude")
    assert "alignment" in claude_page.links
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest test_wiki_builder.py -k "degree or score or plan_pages" -v`
Expected: FAIL — no attribute `degree_map`.

- [ ] **Step 3: Implement**

Append to `backend/wiki_builder.py`:

```python
def degree_map(relationships: list[Relationship]) -> dict[str, int]:
    """Map normalized entity name -> number of incident relationships."""
    deg: dict[str, int] = {}
    for r in relationships:
        deg[normalize_name(r.subject)] = deg.get(normalize_name(r.subject), 0) + 1
        deg[normalize_name(r.object)] = deg.get(normalize_name(r.object), 0) + 1
    return deg


def score_entity(entity: Entity, deg: dict[str, int]) -> float:
    """Significance score deciding whether an entity earns its own page.

    Default heuristic: mentions (chunk count) carry primary weight, graph
    degree (connectedness) is a secondary boost. Monotonic in both.
    """
    mentions = len(entity.chunk_ids)
    degree = deg.get(normalize_name(entity.name), 0)
    return mentions + 0.5 * degree


def plan_pages(
    docs: list[DocRow],
    entities: list[Entity],
    relationships: list[Relationship],
    threshold: float = 2.0,
) -> list[PageSpec]:
    """Decide the page set from the merged graph."""
    deg = degree_map(relationships)
    pages: list[PageSpec] = []

    # 1. Overview (always).
    pages.append(PageSpec(slug="overview", title="Overview", type="overview",
                          related_chunk_ids=[]))

    # 2. Source page per document.
    for d in docs:
        pages.append(PageSpec(
            slug=f"source-{d.document_id}",
            title=d.path.rsplit("/", 1)[-1],
            type="source",
            source_document_id=d.document_id,
        ))

    # 3. Significant entities -> entity/concept pages.
    name_to_slug: dict[str, str] = {}
    for e in entities:
        if score_entity(e, deg) < threshold:
            continue
        slug = slugify(e.name)
        if not slug or slug in {p.slug for p in pages}:
            continue
        page_type = "concept" if e.type == "concept" else "entity"
        pages.append(PageSpec(
            slug=slug, title=e.name, type=page_type,
            entity_name=e.name, related_chunk_ids=list(e.chunk_ids),
        ))
        name_to_slug[normalize_name(e.name)] = slug

    # 4. Relationships -> planned cross-links between pages that exist.
    page_by_slug = {p.slug: p for p in pages}
    for r in relationships:
        s_slug = name_to_slug.get(normalize_name(r.subject))
        o_slug = name_to_slug.get(normalize_name(r.object))
        if s_slug and o_slug and s_slug != o_slug:
            if o_slug not in page_by_slug[s_slug].links:
                page_by_slug[s_slug].links.append(o_slug)
    return pages
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest test_wiki_builder.py -k "degree or score or plan_pages" -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/wiki_builder.py backend/test_wiki_builder.py
git commit -m "feat(wiki): entity scoring + page-set planner"
```

---

## Task 7: Frontmatter + page-writing prompt + link extraction

**Files:**
- Modify: `backend/wiki_builder.py`
- Test: `backend/test_wiki_builder.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/test_wiki_builder.py`:

```python
def test_render_frontmatter():
    spec = wb.PageSpec(slug="claude", title="Claude", type="entity",
                       entity_name="Claude", related_chunk_ids=[7, 8], links=["alignment"])
    fm = wb.render_frontmatter(spec, sources=["card.pdf"])
    assert fm.startswith("---\n")
    assert "title: Claude" in fm
    assert "type: entity" in fm
    assert "felix_refs: [chunk:7, chunk:8]" in fm
    assert fm.rstrip().endswith("---")


def test_extract_wiki_links():
    body = "See [[alignment]] and [[model-welfare]] plus [[alignment]] again."
    assert wb.extract_wiki_links(body) == ["alignment", "model-welfare"]


def test_extract_felix_refs():
    body = "Claude scored 100% [Felix:chunk:7]. It deceived [Felix:chunk:42]."
    assert wb.extract_felix_refs(body) == [7, 42]


def test_build_page_prompt_contains_citation_rules_and_chunks():
    spec = wb.PageSpec(slug="claude", title="Claude", type="entity", entity_name="Claude",
                       related_chunk_ids=[7], links=["alignment"])
    chunks = [wb.ChunkRow(chunk_id=7, document_id=1, content="Scored 100% on Cybench.")]
    system, user = wb.build_page_prompt(spec, chunks, link_titles={"alignment": "Alignment"})
    assert "[Felix:chunk:N]" in system
    assert "[[alignment]]" in user or "[[Alignment]]" in user
    assert "[chunk:7]" in user
    assert "Cybench" in user
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest test_wiki_builder.py -k "frontmatter or wiki_links or felix_refs or page_prompt" -v`
Expected: FAIL — no attribute `render_frontmatter`.

- [ ] **Step 3: Implement**

Append to `backend/wiki_builder.py`:

```python
_PAGE_SYSTEM = """You are writing one page of a structured knowledge wiki built \
from a document corpus. Write clear, factual Markdown.

Hard rules:
- Cite EVERY factual claim with [Felix:chunk:N] using the chunk markers provided.
- Link related wiki pages with [[slug]] using the provided link slugs.
- Start directly with a short intro paragraph, then use ## headings.
- Do NOT invent facts not present in the supplied chunks.
- Do NOT write YAML frontmatter; it is added automatically.
- Be concise; flag contradictions or uncertainty explicitly."""


def render_frontmatter(spec: PageSpec, sources: list[str]) -> str:
    refs = ", ".join(f"chunk:{c}" for c in spec.related_chunk_ids)
    src = ", ".join(sources)
    return (
        "---\n"
        f"title: {spec.title}\n"
        f"type: {spec.type}\n"
        f"sources: [{src}]\n"
        f"felix_refs: [{refs}]\n"
        "---"
    )


def extract_wiki_links(body: str) -> list[str]:
    seen: list[str] = []
    for m in re.findall(r"\[\[([^\]]+)\]\]", body):
        slug = m.strip()
        if slug and slug not in seen:
            seen.append(slug)
    return seen


def extract_felix_refs(body: str) -> list[int]:
    seen: list[int] = []
    for m in re.findall(r"\[Felix:chunk:(\d+)\]", body):
        v = int(m)
        if v not in seen:
            seen.append(v)
    return seen


def build_page_prompt(
    spec: PageSpec, chunks: list[ChunkRow], link_titles: dict[str, str]
) -> tuple[str, str]:
    chunk_text = "\n\n".join(f"[chunk:{c.chunk_id}] {c.content}" for c in chunks)
    links_hint = ", ".join(f"[[{slug}]] ({title})" for slug, title in link_titles.items()) or "(none)"
    user = (
        f"Write the wiki page titled \"{spec.title}\" (type: {spec.type}).\n\n"
        f"Available cross-link slugs you may use where relevant: {links_hint}\n\n"
        f"Source chunks (cite these as [Felix:chunk:N]):\n\n{chunk_text}"
    )
    return _PAGE_SYSTEM, user
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest test_wiki_builder.py -k "frontmatter or wiki_links or felix_refs or page_prompt" -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/wiki_builder.py backend/test_wiki_builder.py
git commit -m "feat(wiki): frontmatter, page prompt, link/citation extraction"
```

---

## Task 8: Lint rules + index/log rendering

**Files:**
- Modify: `backend/wiki_builder.py`
- Test: `backend/test_wiki_builder.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/test_wiki_builder.py`:

```python
def test_find_orphans():
    # pages: overview links to claude; claude links to nothing; ghost has no inbound.
    page_slugs = ["overview", "claude", "ghost"]
    links = [("overview", "claude")]
    orphans = wb.find_orphans(page_slugs, links)
    # overview is a root (exempt); claude has inbound; ghost is an orphan.
    assert orphans == ["ghost"]


def test_render_index_lists_pages_by_type():
    rendered = wb.render_index([
        wb.PageSpec(slug="overview", title="Overview", type="overview"),
        wb.PageSpec(slug="claude", title="Claude", type="entity"),
    ])
    assert "# Wiki Index" in rendered
    assert "[[claude]]" in rendered
    assert "Overview" in rendered
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest test_wiki_builder.py -k "orphans or render_index" -v`
Expected: FAIL — no attribute `find_orphans`.

- [ ] **Step 3: Implement**

Append to `backend/wiki_builder.py`:

```python
ROOT_SLUGS = {"overview", "index", "log"}


def find_orphans(page_slugs: list[str], links: list[tuple[str, str]]) -> list[str]:
    """Pages with no inbound links (root pages exempt)."""
    inbound = {target for _, target in links}
    return [s for s in page_slugs if s not in inbound and s not in ROOT_SLUGS]


def render_index(specs: list[PageSpec]) -> str:
    by_type: dict[str, list[PageSpec]] = {}
    for s in specs:
        by_type.setdefault(s.type, []).append(s)
    lines = ["# Wiki Index", ""]
    for ptype in ["overview", "source", "entity", "concept", "chapter"]:
        group = by_type.get(ptype)
        if not group:
            continue
        lines.append(f"## {ptype.capitalize()}")
        for s in sorted(group, key=lambda x: x.title):
            lines.append(f"- [[{s.slug}]] — {s.title}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_log_entry(timestamp: str, n_docs: int, n_entities: int, n_pages: int) -> str:
    return (
        f"## Build {timestamp}\n"
        f"- documents: {n_docs}\n"
        f"- entities: {n_entities}\n"
        f"- pages: {n_pages}\n"
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest test_wiki_builder.py -k "orphans or render_index" -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/wiki_builder.py backend/test_wiki_builder.py
git commit -m "feat(wiki): lint (orphans) + index/log rendering"
```

---

## Task 9: MiniMax LLM + Azure embedder wrappers

**Files:**
- Modify: `backend/wiki_builder.py`
- Test: `backend/test_wiki_builder.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/test_wiki_builder.py`:

```python
class _FakeChoice:
    def __init__(self, content): self.message = type("M", (), {"content": content})


class _FakeCompletions:
    def __init__(self, content): self._content = content
    async def create(self, **kwargs):
        return type("R", (), {"choices": [_FakeChoice(self._content)]})


class _FakeChatClient:
    def __init__(self, content):
        self.chat = type("C", (), {"completions": _FakeCompletions(content)})


async def test_minimax_llm_complete_returns_content():
    llm = wb.MiniMaxLLM(_FakeChatClient("hello world"), model="MiniMax-M2.7")
    out = await llm.complete("sys", "user")
    assert out == "hello world"


async def test_minimax_llm_handles_none_content():
    llm = wb.MiniMaxLLM(_FakeChatClient(None), model="m")
    assert await llm.complete("s", "u") == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest test_wiki_builder.py -k "minimax" -v`
Expected: FAIL — no attribute `MiniMaxLLM`.

- [ ] **Step 3: Implement**

Append to `backend/wiki_builder.py`:

```python
class MiniMaxLLM:
    """Wraps the search.py AsyncOpenAI MiniMax client as the builder LLM."""
    def __init__(self, client, model: str):
        self._client = client
        self._model = model

    async def complete(self, system: str, user: str) -> str:
        resp = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            stream=False,
        )
        return resp.choices[0].message.content or ""


class AzureEmbedder:
    """Adapts search.py's synchronous AzureOpenAI client to the async Embedder API."""
    def __init__(self, client, model: str):
        self._client = client
        self._model = model

    async def embed(self, text: str) -> list[float]:
        import asyncio
        def _run():
            resp = self._client.embeddings.create(model=self._model, input=text)
            return resp.data[0].embedding
        return await asyncio.to_thread(_run)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest test_wiki_builder.py -k "minimax" -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/wiki_builder.py backend/test_wiki_builder.py
git commit -m "feat(wiki): MiniMax LLM + Azure embedder wrappers"
```

---

## Task 10: Pipeline stages as pure orchestration (LLM/DB injected)

This task assembles stages 1–4 into callable functions that take already-fetched data + injected clients and return results — keeping DB I/O out so the whole pipeline is unit-testable with stubs.

**Files:**
- Modify: `backend/wiki_builder.py`
- Test: `backend/test_wiki_builder.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/test_wiki_builder.py`:

```python
class ScriptedLLM:
    """Returns extraction JSON for extraction prompts, markdown for page prompts."""
    async def complete(self, system, user):
        if "information-extraction engine" in system:
            return ('{"entities": ['
                    '{"name": "Claude", "type": "system", "description": "AI model", "chunk_ids": [1]},'
                    '{"name": "Alignment", "type": "concept", "description": "safety", "chunk_ids": [1, 2]}'
                    '], "relationships": ['
                    '{"subject": "Claude", "predicate": "exhibits", "object": "Alignment", "chunk_ids": [1]}'
                    ']}')
        # page-writing prompt
        return "Intro about the topic [Felix:chunk:1]. See [[alignment]]."


async def test_extract_stage_dedups():
    chunks = [
        wb.ChunkRow(chunk_id=1, document_id=1, content="Claude is aligned."),
        wb.ChunkRow(chunk_id=2, document_id=1, content="Alignment matters."),
    ]
    ents, rels = await wb.run_extract_stage(chunks, ScriptedLLM(), batch_size=5)
    names = sorted(e.name for e in ents)
    assert names == ["Alignment", "Claude"]
    assert len(rels) == 1


async def test_full_pipeline_in_memory():
    docs = [wb.DocRow(document_id=1, path="card.pdf")]
    chunks = [
        wb.ChunkRow(chunk_id=1, document_id=1, content="Claude is aligned."),
        wb.ChunkRow(chunk_id=2, document_id=1, content="Alignment matters."),
    ]
    llm = ScriptedLLM()
    ents, rels = await wb.run_extract_stage(chunks, llm, batch_size=5)
    specs = wb.plan_pages(docs, ents, rels, threshold=1.0)
    written = await wb.run_write_stage(specs, chunks, llm)
    # Every written page has frontmatter + body.
    assert all(w["content_md"].startswith("---\n") for w in written)
    claude = next(w for w in written if w["slug"] == "claude")
    assert "[Felix:chunk:1]" in claude["content_md"]
    assert claude["felix_refs"] == [1]
    assert claude["links"] == ["alignment"]
    # Lint finds no orphan among linked pages (alignment is linked from claude).
    all_links = [(w["slug"], t) for w in written for t in w["links"]]
    orphans = wb.find_orphans([w["slug"] for w in written], all_links)
    assert "alignment" not in orphans
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest test_wiki_builder.py -k "extract_stage or full_pipeline" -v`
Expected: FAIL — no attribute `run_extract_stage`.

- [ ] **Step 3: Implement**

Append to `backend/wiki_builder.py`:

```python
def _batched(items: list, n: int):
    for i in range(0, len(items), n):
        yield items[i:i + n]


async def run_extract_stage(
    chunks: list[ChunkRow], llm: LLM, batch_size: int = 5
) -> tuple[list[Entity], list[Relationship]]:
    all_entities: list[Entity] = []
    all_rels: list[Relationship] = []
    for batch in _batched(chunks, batch_size):
        system, user = build_extraction_prompt(batch)
        raw = await llm.complete(system, user)
        ents, rels = parse_extraction(raw, [c.chunk_id for c in batch])
        all_entities.extend(ents)
        all_rels.extend(rels)
    return merge_entities_by_name(all_entities), all_rels


async def run_write_stage(
    specs: list[PageSpec], all_chunks: list[ChunkRow], llm: LLM
) -> list[dict]:
    """Write each page. Returns dicts ready for persistence."""
    chunk_by_id = {c.chunk_id: c for c in all_chunks}
    title_by_slug = {s.slug: s.title for s in specs}
    written: list[dict] = []
    for spec in specs:
        if spec.type == "source" and spec.source_document_id is not None:
            relevant = [c for c in all_chunks if c.document_id == spec.source_document_id]
        elif spec.type == "overview":
            relevant = all_chunks[:20]
        else:
            relevant = [chunk_by_id[c] for c in spec.related_chunk_ids if c in chunk_by_id]
        link_titles = {slug: title_by_slug.get(slug, slug) for slug in spec.links}
        system, user = build_page_prompt(spec, relevant, link_titles)
        body = await llm.complete(system, user)
        sources = sorted({chunk_by_id[c].document_id for c in extract_felix_refs(body) if c in chunk_by_id})
        frontmatter = render_frontmatter(spec, sources=[f"doc:{d}" for d in sources] or ["corpus"])
        links = sorted(set(spec.links) | set(extract_wiki_links(body)))
        written.append({
            "slug": spec.slug,
            "title": spec.title,
            "type": spec.type,
            "content_md": f"{frontmatter}\n\n{body}",
            "felix_refs": extract_felix_refs(body),
            "entity_name": spec.entity_name,
            "links": links,
        })
    return written
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest test_wiki_builder.py -v`
Expected: PASS (all tests across the module).

- [ ] **Step 5: Commit**

```bash
git add backend/wiki_builder.py backend/test_wiki_builder.py
git commit -m "feat(wiki): extract + write pipeline stages (stub-testable)"
```

---

# Phase 3 — Persistence, Orchestrator, API

## Task 11: DB fetch + persistence helpers (asyncpg)

**Files:**
- Modify: `backend/wiki_builder.py`
- Test: `backend/test_wiki_builder.py` (mock-pool tests)

- [ ] **Step 1: Write the failing test**

Append to `backend/test_wiki_builder.py`. Reuse the mock-pool style from `conftest.py`:

```python
class _MockConn:
    def __init__(self, responses):
        self.responses = responses
        self.executed = []
    async def fetch(self, q, *a):
        return self.responses.get("fetch", [])
    async def fetchrow(self, q, *a):
        return self.responses.get("fetchrow", None)
    async def fetchval(self, q, *a):
        vals = self.responses.get("fetchval", [])
        return vals.pop(0) if isinstance(vals, list) and vals else vals
    async def execute(self, q, *a):
        self.executed.append((q, a))
    def transaction(self):
        conn = self
        class _Tx:
            async def __aenter__(self): return conn
            async def __aexit__(self, *exc): return False
        return _Tx()


async def test_fetch_index_chunks_maps_rows():
    conn = _MockConn({"fetch": [
        {"chunk_id": 1, "document_id": 9, "content": "hello", "headings": ["H1"]},
    ]})
    rows = await wb.fetch_index_chunks(conn, index_id=3)
    assert rows[0].chunk_id == 1 and rows[0].document_id == 9
    assert rows[0].headings == ["H1"]


async def test_resolve_index_id():
    conn = _MockConn({"fetchval": [42]})
    assert await wb.resolve_index_id(conn, "default") == 42


async def test_resolve_index_id_missing_raises():
    conn = _MockConn({"fetchval": [None]})
    import pytest
    with pytest.raises(ValueError):
        await wb.resolve_index_id(conn, "nope")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest test_wiki_builder.py -k "fetch_index_chunks or resolve_index" -v`
Expected: FAIL — no attribute `fetch_index_chunks`.

- [ ] **Step 3: Implement**

Append to `backend/wiki_builder.py`:

```python
async def resolve_index_id(conn, slug: str) -> int:
    idx = await conn.fetchval("SELECT id FROM indexes WHERE slug = $1", slug)
    if idx is None:
        raise ValueError(f"Index '{slug}' not found")
    return idx


async def fetch_index_docs(conn, index_id: int) -> list[DocRow]:
    rows = await conn.fetch(
        "SELECT id, path FROM documents WHERE index_id = $1 ORDER BY id", index_id)
    return [DocRow(document_id=r["id"], path=r["path"]) for r in rows]


async def fetch_index_chunks(conn, index_id: int) -> list[ChunkRow]:
    rows = await conn.fetch(
        """SELECT c.id AS chunk_id, c.document_id, c.content, c.headings
           FROM chunks c JOIN documents d ON d.id = c.document_id
           WHERE d.index_id = $1 ORDER BY c.document_id, c.chunk_index""",
        index_id)
    return [ChunkRow(chunk_id=r["chunk_id"], document_id=r["document_id"],
                     content=r["content"], headings=list(r["headings"] or []))
            for r in rows]


async def clear_wiki(conn, index_id: int) -> None:
    # wiki_links / entity_chunks / relationships cascade from pages & entities.
    await conn.execute("DELETE FROM wiki_pages WHERE index_id = $1", index_id)
    await conn.execute("DELETE FROM wiki_entities WHERE index_id = $1", index_id)


async def persist_entities(conn, index_id: int, entities: list[Entity]) -> dict[str, int]:
    """Insert entities, return normalized_name -> entity_id."""
    name_to_id: dict[str, int] = {}
    for e in entities:
        eid = await conn.fetchval(
            """INSERT INTO wiki_entities
                 (index_id, name, normalized_name, type, description, mention_count)
               VALUES ($1, $2, $3, $4, $5, $6)
               ON CONFLICT (index_id, normalized_name) DO UPDATE SET
                 description = EXCLUDED.description, mention_count = EXCLUDED.mention_count
               RETURNING id""",
            index_id, e.name, normalize_name(e.name), e.type, e.description, len(e.chunk_ids))
        name_to_id[normalize_name(e.name)] = eid
        for cid in e.chunk_ids:
            await conn.execute(
                "INSERT INTO entity_chunks (entity_id, chunk_id) VALUES ($1, $2) "
                "ON CONFLICT DO NOTHING", eid, cid)
    return name_to_id


async def persist_relationships(conn, index_id: int, rels: list[Relationship],
                                name_to_id: dict[str, int]) -> None:
    for r in rels:
        s = name_to_id.get(normalize_name(r.subject))
        o = name_to_id.get(normalize_name(r.object))
        if s is None or o is None:
            continue
        await conn.execute(
            """INSERT INTO wiki_relationships
                 (index_id, subject_entity_id, predicate, object_entity_id, description, chunk_refs)
               VALUES ($1, $2, $3, $4, $5, $6)""",
            index_id, s, r.predicate, o, r.description, r.chunk_ids)


async def persist_pages(conn, index_id: int, written: list[dict],
                        name_to_id: dict[str, int]) -> None:
    slug_to_id: dict[str, int] = {}
    for w in written:
        entity_id = name_to_id.get(normalize_name(w["entity_name"])) if w["entity_name"] else None
        pid = await conn.fetchval(
            """INSERT INTO wiki_pages
                 (index_id, slug, title, type, content_md, felix_refs, entity_id)
               VALUES ($1, $2, $3, $4, $5, $6, $7)
               ON CONFLICT (index_id, slug) DO UPDATE SET
                 content_md = EXCLUDED.content_md, felix_refs = EXCLUDED.felix_refs,
                 updated_at = NOW()
               RETURNING id""",
            index_id, w["slug"], w["title"], w["type"], w["content_md"],
            w["felix_refs"], entity_id)
        slug_to_id[w["slug"]] = pid
    # Links (resolve targets where possible).
    for w in written:
        src = slug_to_id[w["slug"]]
        for target in w["links"]:
            await conn.execute(
                "INSERT INTO wiki_links (source_page_id, target_page_id, target_slug) "
                "VALUES ($1, $2, $3)", src, slug_to_id.get(target), target)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest test_wiki_builder.py -k "fetch_index_chunks or resolve_index" -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/wiki_builder.py backend/test_wiki_builder.py
git commit -m "feat(wiki): asyncpg fetch + persistence helpers"
```

---

## Task 12: `run_wiki_build` orchestrator + job status updates

**Files:**
- Modify: `backend/wiki_builder.py`
- Test: `backend/test_wiki_builder.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/test_wiki_builder.py`:

```python
async def test_update_job_sets_fields():
    conn = _MockConn({})
    await wb.update_job(conn, job_id=5, status="extracting", progress={"docs": 2})
    q, args = conn.executed[-1]
    assert "UPDATE wiki_jobs" in q
    assert 5 in args


async def test_set_job_started_and_completed_helpers():
    conn = _MockConn({})
    await wb.update_job(conn, job_id=1, status="completed")
    q, _ = conn.executed[-1]
    assert "completed_at = NOW()" in q
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest test_wiki_builder.py -k "update_job or job_started" -v`
Expected: FAIL — no attribute `update_job`.

- [ ] **Step 3: Implement**

Append to `backend/wiki_builder.py`:

```python
async def update_job(conn, job_id: int, status: str, progress: dict | None = None,
                     error_message: str | None = None) -> None:
    sets = ["status = $2", "updated_at = NOW()"]
    params = [job_id, status]
    n = 3
    if progress is not None:
        sets.append(f"progress = progress || ${n}::jsonb")
        params.append(json.dumps(progress)); n += 1
    if error_message is not None:
        sets.append(f"error_message = ${n}")
        params.append(error_message); n += 1
    sets.append("started_at = COALESCE(started_at, CASE WHEN $2 != 'queued' THEN NOW() ELSE NULL END)")
    if status in ("completed", "failed"):
        sets.append("completed_at = NOW()")
    await conn.execute(f"UPDATE wiki_jobs SET {', '.join(sets)} WHERE id = $1", *params)


async def run_wiki_build(pool, llm: LLM, embedder: Embedder | None,
                         index_slug: str, job_id: int, timestamp: str) -> None:
    """Top-level orchestrator. Advances wiki_jobs through the pipeline. Never raises;
    failures are recorded on the job row."""
    try:
        async with pool.acquire() as conn:
            index_id = await resolve_index_id(conn, index_slug)
            docs = await fetch_index_docs(conn, index_id)
            chunks = await fetch_index_chunks(conn, index_id)
            await clear_wiki(conn, index_id)

        await _with_job(pool, job_id, "extracting", {"documents": len(docs)})
        entities, rels = await run_extract_stage(chunks, llm)
        if embedder is not None and entities:
            entities = await merge_entities_by_embedding(entities, embedder)

        await _with_job(pool, job_id, "planning", {"entities": len(entities)})
        specs = plan_pages(docs, entities, rels)

        await _with_job(pool, job_id, "writing", {"pages": len(specs)})
        written = await run_write_stage(specs, chunks, llm)

        async with pool.acquire() as conn:
            async with conn.transaction():
                name_to_id = await persist_entities(conn, index_id, entities)
                await persist_relationships(conn, index_id, rels, name_to_id)
                await persist_pages(conn, index_id, written, name_to_id)
                # index + log pages.
                idx_md = render_index(specs)
                await persist_pages(conn, index_id, [{
                    "slug": "index", "title": "Wiki Index", "type": "index",
                    "content_md": idx_md, "felix_refs": [], "entity_name": None, "links": [],
                }], name_to_id)

        await _with_job(pool, job_id, "linting", {})
        all_links = [(w["slug"], t) for w in written for t in w["links"]]
        orphans = find_orphans([w["slug"] for w in written], all_links)

        await _with_job(pool, job_id, "completed",
                        {"pages": len(written), "entities": len(entities), "orphans": orphans})
    except Exception as e:  # noqa: BLE001 — record failure on the job, never crash worker
        async with pool.acquire() as conn:
            await update_job(conn, job_id, "failed", error_message=str(e))


async def _with_job(pool, job_id: int, status: str, progress: dict) -> None:
    async with pool.acquire() as conn:
        await update_job(conn, job_id, status, progress=progress)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest test_wiki_builder.py -v`
Expected: PASS (all module tests).

- [ ] **Step 5: Commit**

```bash
git add backend/wiki_builder.py backend/test_wiki_builder.py
git commit -m "feat(wiki): build orchestrator + job state-machine updates"
```

---

## Task 13: Wiki API endpoints in search.py

**Files:**
- Modify: `backend/search.py`
- Test: `backend/test_wiki_api.py`

- [ ] **Step 1: Write the failing test**

Create `backend/test_wiki_api.py`:

```python
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from conftest import make_mock_pool


@pytest_asyncio.fixture
async def client_for(monkeypatch):
    async def _make(responses):
        import search as s
        pool = make_mock_pool(responses)
        s.db_pool = pool
        transport = ASGITransport(app=s.app)
        return AsyncClient(transport=transport, base_url="http://test")
    yield _make
    import search as s
    s.db_pool = None


async def test_list_wiki_pages(client_for):
    rows = [{"slug": "overview", "title": "Overview", "type": "overview"}]
    client = await client_for({"fetch": rows, "fetchval": [1]})
    resp = await client.get("/indexes/default/wiki")
    assert resp.status_code == 200
    assert resp.json()["pages"][0]["slug"] == "overview"


async def test_get_wiki_page(client_for):
    page = {"slug": "claude", "title": "Claude", "type": "entity",
            "content_md": "---\ntitle: Claude\n---\n\nBody [Felix:chunk:1]."}
    client = await client_for({"fetchrow": page, "fetch": [], "fetchval": [1]})
    resp = await client.get("/indexes/default/wiki/pages/claude")
    assert resp.status_code == 200
    assert resp.json()["title"] == "Claude"


async def test_get_wiki_page_404(client_for):
    client = await client_for({"fetchrow": None, "fetchval": [1]})
    resp = await client.get("/indexes/default/wiki/pages/missing")
    assert resp.status_code == 404


async def test_build_wiki_enqueues(client_for, monkeypatch):
    import search as s
    started = {}
    monkeypatch.setattr(s.asyncio, "create_task", lambda coro: started.setdefault("task", coro) or coro.close())
    client = await client_for({"fetchval": [1, 77]})  # index_id, then job_id
    resp = await client.post("/indexes/default/wiki/build")
    assert resp.status_code == 200
    assert resp.json()["job_id"] == 77
    assert resp.json()["status"] == "queued"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest test_wiki_api.py -v`
Expected: FAIL — 404 on `/indexes/default/wiki` (endpoint not defined).

- [ ] **Step 3: Implement the endpoints**

Add near the other endpoints in `backend/search.py` (after the `/indexes` endpoints). First ensure imports at top of file include the builder:

```python
import wiki_builder as wiki
```

Then add:

```python
def _build_llm():
    return wiki.MiniMaxLLM(_chat_client, _CHAT_MODEL)


def _build_embedder():
    return wiki.AzureEmbedder(get_openai_client(), AZURE_EMBEDDING_MODEL)


@app.post("/indexes/{slug}/wiki/build")
async def build_wiki(slug: str):
    """Enqueue an autonomous wiki build for an index."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        index_id = await conn.fetchval("SELECT id FROM indexes WHERE slug = $1", slug)
        if index_id is None:
            raise HTTPException(status_code=404, detail=f"Index '{slug}' not found")
        job_id = await conn.fetchval(
            "INSERT INTO wiki_jobs (index_id, status) VALUES ($1, 'queued') RETURNING id",
            index_id)

    from datetime import datetime, timezone
    ts = datetime.now(timezone.utc).isoformat()
    asyncio.create_task(
        wiki.run_wiki_build(pool, _build_llm(), _build_embedder(), slug, job_id, ts))
    return {"job_id": job_id, "status": "queued", "index_slug": slug}


@app.get("/indexes/{slug}/wiki")
async def list_wiki_pages(slug: str):
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        index_id = await conn.fetchval("SELECT id FROM indexes WHERE slug = $1", slug)
        if index_id is None:
            raise HTTPException(status_code=404, detail=f"Index '{slug}' not found")
        rows = await conn.fetch(
            "SELECT slug, title, type FROM wiki_pages WHERE index_id = $1 ORDER BY type, title",
            index_id)
        return {"pages": [dict(r) for r in rows]}


@app.get("/indexes/{slug}/wiki/pages/{page_slug}")
async def get_wiki_page(slug: str, page_slug: str):
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        index_id = await conn.fetchval("SELECT id FROM indexes WHERE slug = $1", slug)
        if index_id is None:
            raise HTTPException(status_code=404, detail=f"Index '{slug}' not found")
        row = await conn.fetchrow(
            "SELECT slug, title, type, content_md, felix_refs FROM wiki_pages "
            "WHERE index_id = $1 AND slug = $2", index_id, page_slug)
        if row is None:
            raise HTTPException(status_code=404, detail=f"Page '{page_slug}' not found")
        links = await conn.fetch(
            "SELECT wl.target_slug, wp.title FROM wiki_links wl "
            "JOIN wiki_pages src ON src.id = wl.source_page_id "
            "LEFT JOIN wiki_pages wp ON wp.id = wl.target_page_id "
            "WHERE src.index_id = $1 AND src.slug = $2", index_id, page_slug)
        return {**dict(row), "links": [dict(l) for l in links]}


@app.get("/indexes/{slug}/wiki/graph")
async def get_wiki_graph(slug: str):
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        index_id = await conn.fetchval("SELECT id FROM indexes WHERE slug = $1", slug)
        if index_id is None:
            raise HTTPException(status_code=404, detail=f"Index '{slug}' not found")
        ents = await conn.fetch(
            "SELECT id, name, type, mention_count FROM wiki_entities WHERE index_id = $1", index_id)
        rels = await conn.fetch(
            "SELECT subject_entity_id, object_entity_id, predicate "
            "FROM wiki_relationships WHERE index_id = $1", index_id)
        nodes = [{"id": e["id"], "label": e["name"], "type": e["type"],
                  "weight": e["mention_count"]} for e in ents]
        edges = [{"source": r["subject_entity_id"], "target": r["object_entity_id"],
                  "label": r["predicate"]} for r in rels]
        return {"nodes": nodes, "edges": edges}


@app.get("/indexes/{slug}/wiki/status")
async def wiki_status(slug: str):
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """SELECT j.id, j.status, j.progress, j.error_message,
                      j.created_at, j.completed_at
               FROM wiki_jobs j JOIN indexes i ON i.id = j.index_id
               WHERE i.slug = $1 ORDER BY j.created_at DESC LIMIT 1""", slug)
        if row is None:
            return {"status": "none"}
        d = dict(row)
        d["progress"] = json.loads(d["progress"]) if isinstance(d["progress"], str) else d["progress"]
        for k in ("created_at", "completed_at"):
            d[k] = d[k].isoformat() if d[k] else None
        return d


@app.delete("/indexes/{slug}/wiki")
async def delete_wiki(slug: str):
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        index_id = await conn.fetchval("SELECT id FROM indexes WHERE slug = $1", slug)
        if index_id is None:
            raise HTTPException(status_code=404, detail=f"Index '{slug}' not found")
        await conn.execute("DELETE FROM wiki_pages WHERE index_id = $1", index_id)
        await conn.execute("DELETE FROM wiki_entities WHERE index_id = $1", index_id)
    return {"deleted": True, "index_slug": slug}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest test_wiki_api.py -v`
Expected: PASS (4 tests). If `make_mock_pool` is not importable, confirm it is defined in `conftest.py` and exported (it is used by the existing `client` fixture).

- [ ] **Step 5: Commit**

```bash
git add backend/search.py backend/test_wiki_api.py
git commit -m "feat(wiki): wiki build/list/page/graph/status/delete endpoints"
```

---

## Task 14: SSE build-progress endpoint

**Files:**
- Modify: `backend/search.py`
- Test: `backend/test_wiki_api.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/test_wiki_api.py`:

```python
async def test_wiki_stream_is_event_stream(client_for):
    client = await client_for({"fetchrow": {"id": 1, "status": "writing", "progress": {},
                                            "error_message": None}, "fetchval": [1]})
    async with client.stream("GET", "/indexes/default/wiki/stream") as resp:
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        break_after = False
        async for line in resp.aiter_lines():
            if line.startswith("data:") or line.startswith(":"):
                break_after = True
                break
        assert break_after
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest test_wiki_api.py -k stream -v`
Expected: FAIL — 404 (no stream endpoint).

- [ ] **Step 3: Implement (mirror `/ingestion/stream`)**

Add to `backend/search.py`:

```python
@app.get("/indexes/{slug}/wiki/stream")
async def wiki_stream(slug: str):
    """SSE progress for the latest wiki build of an index."""
    async def event_generator():
        last = None
        pool = await get_db_pool()
        while True:
            try:
                async with pool.acquire() as conn:
                    row = await conn.fetchrow(
                        """SELECT j.id, j.status, j.progress, j.error_message
                           FROM wiki_jobs j JOIN indexes i ON i.id = j.index_id
                           WHERE i.slug = $1 ORDER BY j.created_at DESC LIMIT 1""", slug)
                if row is None:
                    payload = {"status": "none"}
                else:
                    d = dict(row)
                    d["progress"] = (json.loads(d["progress"])
                                     if isinstance(d["progress"], str) else d["progress"])
                    payload = d
                current = json.dumps(payload, sort_keys=True, default=str)
                if current != last:
                    yield f"data: {json.dumps(payload, default=str)}\n\n"
                    last = current
                else:
                    yield ": keepalive\n\n"
                if payload.get("status") in ("completed", "failed"):
                    await asyncio.sleep(2)
            except Exception as e:
                logger.warning("wiki_sse_poll_error", error=str(e))
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
            await asyncio.sleep(2)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive",
                 "X-Accel-Buffering": "no"},
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest test_wiki_api.py -k stream -v`
Expected: PASS (1 test).

- [ ] **Step 5: Commit**

```bash
git add backend/search.py backend/test_wiki_api.py
git commit -m "feat(wiki): SSE build-progress endpoint"
```

---

## Task 15: Full backend suite + real end-to-end build

**Files:** none (verification task)

- [ ] **Step 1: Run the entire backend suite**

Run: `cd backend && pytest -v`
Expected: PASS — all pre-existing (57) + new wiki tests.

- [ ] **Step 2: Run a real build against the dev stack**

With `docker compose up -d` running and at least one document ingested into the `default` index:
```bash
curl -s -X POST http://localhost:8001/indexes/default/wiki/build | tee /tmp/wiki_build.json
curl -s http://localhost:8001/indexes/default/wiki/status
```
Expected: build returns a `job_id`; status advances `extracting → planning → writing → linting → completed`. (This makes real MiniMax calls — confirm `MINIMAX_API_KEY` is set.)

- [ ] **Step 3: Inspect output**

```bash
curl -s http://localhost:8001/indexes/default/wiki | python -m json.tool
curl -s http://localhost:8001/indexes/default/wiki/pages/overview | python -m json.tool
```
Expected: a page list including `overview`/`index`/source/entity pages; the overview page body contains `[Felix:chunk:N]` citations.

- [ ] **Step 4: Commit any fixes discovered**

```bash
git add -A && git commit -m "fix(wiki): address issues found in end-to-end build"
```
(Skip if nothing changed.)

---

# Phase 4 — Frontend

## Task 16: Wiki API client functions

**Files:**
- Modify: `frontend/src/api/client.jsx`

- [ ] **Step 1: Add the client functions**

Append to `frontend/src/api/client.jsx` (matching the existing fetch-wrapper style):

```javascript
export const buildWiki = async (indexSlug) => {
  const response = await fetch(`${API_URL}/indexes/${encodeURIComponent(indexSlug)}/wiki/build`, {
    method: 'POST',
  })
  return response.json()
}

export const getWikiPages = async (indexSlug) => {
  const response = await fetch(`${API_URL}/indexes/${encodeURIComponent(indexSlug)}/wiki`)
  return response.json()
}

export const getWikiPage = async (indexSlug, pageSlug) => {
  const response = await fetch(
    `${API_URL}/indexes/${encodeURIComponent(indexSlug)}/wiki/pages/${encodeURIComponent(pageSlug)}`)
  return response.json()
}

export const getWikiGraph = async (indexSlug) => {
  const response = await fetch(`${API_URL}/indexes/${encodeURIComponent(indexSlug)}/wiki/graph`)
  return response.json()
}

export const getWikiStatus = async (indexSlug) => {
  const response = await fetch(`${API_URL}/indexes/${encodeURIComponent(indexSlug)}/wiki/status`)
  return response.json()
}

export const wikiStreamUrl = (indexSlug) =>
  `${API_URL}/indexes/${encodeURIComponent(indexSlug)}/wiki/stream`
```

- [ ] **Step 2: Verify the frontend still builds**

Run: `cd frontend && npm run build`
Expected: build succeeds.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/client.jsx
git commit -m "feat(wiki): frontend API client functions"
```

---

## Task 17: `useWikiBuild` SSE hook

**Files:**
- Create: `frontend/src/hooks/useWikiBuild.js`

- [ ] **Step 1: Implement the hook (mirrors `useIngestionStatus`)**

Create `frontend/src/hooks/useWikiBuild.js`:

```javascript
import { useCallback, useEffect, useRef, useState } from 'react'
import { wikiStreamUrl, getWikiStatus } from '../api/client'

export default function useWikiBuild(indexSlug) {
  const [job, setJob] = useState(null)
  const [connected, setConnected] = useState(false)
  const esRef = useRef(null)

  const connect = useCallback(() => {
    if (!indexSlug) return
    if (esRef.current) esRef.current.close()
    const es = new EventSource(wikiStreamUrl(indexSlug))
    esRef.current = es
    es.onopen = () => setConnected(true)
    es.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        if (data.error) return
        setJob(data)
      } catch { /* keepalive */ }
    }
    es.onerror = () => {
      setConnected(false)
      es.close()
      esRef.current = null
    }
  }, [indexSlug])

  useEffect(() => {
    if (!indexSlug) return
    getWikiStatus(indexSlug).then(setJob).catch(() => {})
    connect()
    return () => { if (esRef.current) esRef.current.close() }
  }, [indexSlug, connect])

  return { job, connected, reconnect: connect }
}
```

- [ ] **Step 2: Verify build**

Run: `cd frontend && npm run build`
Expected: build succeeds.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/hooks/useWikiBuild.js
git commit -m "feat(wiki): useWikiBuild SSE progress hook"
```

---

## Task 18: Wiki viewer component + nav + route

**Files:**
- Create: `frontend/src/components/Wiki.jsx`
- Modify: `frontend/src/AppShell.jsx`, `frontend/src/App.jsx`

- [ ] **Step 1: Create the Wiki component**

Create `frontend/src/components/Wiki.jsx`:

```javascript
import { useState, useEffect, useCallback } from 'react'
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { useNavigate } from 'react-router-dom'
import { getIndexes, getWikiPages, getWikiPage, buildWiki } from '../api/client'
import useWikiBuild from '../hooks/useWikiBuild'
import { ScrollArea } from '@/components/ui/scroll-area'

const CITATION_RE = /\[Felix:chunk:(\d+)\]/g

function Wiki() {
  const [indexSlug, setIndexSlug] = useState('default')
  const [indexes, setIndexes] = useState([])
  const [pages, setPages] = useState([])
  const [selected, setSelected] = useState(null)
  const [page, setPage] = useState(null)
  const navigate = useNavigate()
  const { job } = useWikiBuild(indexSlug)

  useEffect(() => { getIndexes().then(d => setIndexes(d || [])).catch(() => {}) }, [])

  const loadPages = useCallback(() => {
    getWikiPages(indexSlug).then(d => setPages(d.pages || [])).catch(() => {})
  }, [indexSlug])

  useEffect(() => { loadPages() }, [loadPages])
  useEffect(() => {
    if (job?.status === 'completed') loadPages()
  }, [job?.status, loadPages])

  const openPage = async (slug) => {
    setSelected(slug)
    const data = await getWikiPage(indexSlug, slug)
    setPage(data)
  }

  // Render markdown, turning [[slug]] into in-wiki links and [Felix:chunk:N]
  // into clickable citations that route to the document viewer.
  const renderBody = (md) => {
    if (!md) return md
    // Strip frontmatter for display.
    const body = md.replace(/^---\n[\s\S]*?\n---\n*/, '')
    return body.replace(CITATION_RE, (_, n) => `[\`chunk:${n}\`](#chunk-${n})`)
                .replace(/\[\[([^\]]+)\]\]/g, (_, s) => `[${s}](#wiki-${s})`)
  }

  const onLinkClick = (href) => {
    if (href?.startsWith('#wiki-')) { openPage(href.slice(6)); return false }
    if (href?.startsWith('#chunk-')) { navigate(`/documents/1?chunk=${href.slice(7)}`); return false }
    return true
  }

  const byType = pages.reduce((acc, p) => {
    (acc[p.type] ||= []).push(p); return acc
  }, {})

  return (
    <div className="max-w-6xl mx-auto px-6 py-8">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-lg font-semibold text-warm-900">Wiki</h1>
          <p className="text-xs text-warm-500 mt-0.5">Autonomously built from your index</p>
        </div>
        <div className="flex items-center gap-2">
          <select value={indexSlug} onChange={e => setIndexSlug(e.target.value)}
            className="text-xs border border-warm-200 rounded-md px-2 py-1.5">
            {indexes.map(i => <option key={i.slug} value={i.slug}>{i.display_name || i.slug}</option>)}
          </select>
          <button onClick={() => buildWiki(indexSlug)}
            className="px-3 py-1.5 text-xs font-medium rounded-md bg-ember text-white hover:opacity-90">
            Build Wiki
          </button>
        </div>
      </div>

      {job && job.status && job.status !== 'completed' && job.status !== 'none' && (
        <div className="mb-4 text-xs text-ember">Building… {job.status}
          {job.progress?.pages ? ` (${job.progress.pages} pages)` : ''}</div>
      )}

      <div className="grid gap-6 grid-cols-1 lg:grid-cols-4">
        <div className="bg-white rounded-xl shadow-sm overflow-hidden">
          <div className="px-6 pt-5 pb-4">
            <h2 className="text-xs font-medium text-warm-500 uppercase tracking-wider">Pages</h2>
          </div>
          <ScrollArea className="h-[28rem]">
            <div className="px-3 pb-3 space-y-3">
              {Object.entries(byType).map(([type, group]) => (
                <div key={type}>
                  <div className="px-3 text-[10px] uppercase tracking-wider text-warm-400">{type}</div>
                  {group.map(p => (
                    <button key={p.slug} onClick={() => openPage(p.slug)}
                      className={`w-full text-left px-3 py-2 text-xs rounded-lg transition-colors ${
                        selected === p.slug ? 'text-ember bg-ember/[0.08]'
                          : 'text-warm-600 hover:text-warm-900 hover:bg-warm-50'}`}>
                      {p.title}
                    </button>
                  ))}
                </div>
              ))}
              {pages.length === 0 && (
                <p className="text-sm text-warm-500 px-3 py-6 text-center">
                  No wiki yet. Click “Build Wiki”.</p>
              )}
            </div>
          </ScrollArea>
        </div>

        <div className="lg:col-span-3 bg-white rounded-xl shadow-sm overflow-hidden">
          {!selected && (
            <div className="px-6 py-12 text-center">
              <p className="text-sm text-warm-500">Select a page to view</p>
            </div>
          )}
          {selected && page && (
            <div className="px-6 py-6 prose prose-sm max-w-none">
              <Markdown remarkPlugins={[remarkGfm]} components={{
                a: ({ href, children }) => (
                  <a href={href} onClick={(e) => { if (onLinkClick(href) === false) e.preventDefault() }}>
                    {children}
                  </a>
                ),
              }}>
                {renderBody(page.content_md)}
              </Markdown>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default Wiki
```

- [ ] **Step 2: Add the nav item**

In `frontend/src/AppShell.jsx`, add to `NAV_ITEMS`:

```javascript
const NAV_ITEMS = [
  { to: '/documents', label: 'Documents' },
  { to: '/search', label: 'Search' },
  { to: '/wiki', label: 'Wiki' },
  { to: '/chat', label: 'Chat' },
]
```

- [ ] **Step 3: Add the route**

In `frontend/src/App.jsx`, add the import and the route + wrapper inside the `<Route element={<AppShell />}>` group:

```javascript
import Wiki from './components/Wiki'

function WikiPage() {
  return <Wiki />
}
```
And within the AppShell route group:
```javascript
<Route path="/wiki" element={<WikiPage />} />
```

- [ ] **Step 4: Verify build**

Run: `cd frontend && npm run build`
Expected: build succeeds.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/Wiki.jsx frontend/src/AppShell.jsx frontend/src/App.jsx
git commit -m "feat(wiki): wiki viewer + nav item + route"
```

---

## Task 19: Citation/link navigation component test

**Files:**
- Create: `frontend/src/components/Wiki.test.jsx`

> Confirm the test runner first: check `frontend/package.json` for a `test` script
> (vitest or jest). If none exists, add `"test": "vitest"` and dev-deps
> `vitest @testing-library/react @testing-library/jest-dom jsdom`, and a minimal
> `vitest.config.js` with `environment: 'jsdom'`. If the project has no frontend test
> infra and the user prefers not to add it, SKIP this task and rely on manual
> verification in Task 20.

- [ ] **Step 1: Write the test**

Create `frontend/src/components/Wiki.test.jsx`:

```javascript
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import Wiki from './Wiki'
import * as client from '../api/client'

vi.mock('../hooks/useWikiBuild', () => ({ default: () => ({ job: null, connected: false }) }))

beforeEach(() => {
  vi.spyOn(client, 'getIndexes').mockResolvedValue([{ slug: 'default', display_name: 'Default' }])
  vi.spyOn(client, 'getWikiPages').mockResolvedValue({
    pages: [{ slug: 'overview', title: 'Overview', type: 'overview' },
            { slug: 'claude', title: 'Claude', type: 'entity' }],
  })
  vi.spyOn(client, 'getWikiPage').mockResolvedValue({
    slug: 'overview', title: 'Overview', type: 'overview',
    content_md: '---\ntitle: Overview\n---\n\nIntro [Felix:chunk:7]. See [[claude]].',
  })
})

describe('Wiki', () => {
  it('lists pages and opens one with rendered citations + wiki links', async () => {
    render(<MemoryRouter><Wiki /></MemoryRouter>)
    await waitFor(() => expect(screen.getByText('Overview')).toBeInTheDocument())
    fireEvent.click(screen.getByText('Overview'))
    await waitFor(() => expect(screen.getByText(/chunk:7/)).toBeInTheDocument())
    // The [[claude]] link renders as an anchor labeled "claude".
    expect(screen.getByText('claude')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run the test**

Run: `cd frontend && npm run test -- --run`
Expected: PASS (1 test).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/Wiki.test.jsx frontend/package.json frontend/vitest.config.js
git commit -m "test(wiki): viewer citation/link navigation"
```

---

## Task 20: End-to-end manual verification

**Files:** none (verification)

- [ ] **Step 1: Bring up the stack and build a wiki**

```bash
docker compose up -d
# ingest at least one document into 'default' if not already present
```
Open http://localhost:5180 → Wiki tab → select an index → click **Build Wiki**.

- [ ] **Step 2: Observe progress + result**

Expected: status line advances through `extracting/planning/writing/linting`; on completion the page tree populates with Overview, Index, source, entity, and concept pages.

- [ ] **Step 3: Verify navigation**

Click a page → confirm `[[links]]` navigate within the wiki and `chunk:N` citations route to the document viewer. Toggle/inspect the graph endpoint:
```bash
curl -s http://localhost:8001/indexes/default/wiki/graph | python -m json.tool
```
Expected: `nodes` (entities) + `edges` (relationships).

- [ ] **Step 4: Final commit / branch wrap-up**

Use the `superpowers:finishing-a-development-branch` skill to decide merge/PR.

---

## Self-Review Notes

- **Spec coverage:** schema (Task 1), extraction+dedup (Tasks 3–5, 10), planner+`score_entity` (Task 6), writing+citations (Tasks 7, 10), lint+index/log (Task 8), orchestrator+jobs (Task 12), all 7 endpoints incl. SSE (Tasks 13–14), frontend viewer+graph+build (Tasks 16–19), tests throughout. Incremental updates explicitly deferred per spec.
- **Type consistency:** `Entity/Relationship/ChunkRow/DocRow/PageSpec` defined in Task 2 and used unchanged thereafter; `run_write_stage` returns dicts with keys `slug/title/type/content_md/felix_refs/entity_name/links` consumed identically by `persist_pages` (Task 11) and the orchestrator (Task 12).
- **No placeholders:** every code step is complete; `score_entity` ships a working default with a learning-mode revision checkpoint (contract pinned by test).
- **GraphRAG depth:** lightweight entity-graph only (community detection out of scope, per spec).
- **Graph view:** the `/wiki/graph` endpoint (Task 13) ships `{nodes, edges}` in Phase 3. The force-directed visual component is deliberately follow-on — it reuses the existing `useForceLayout` and needs no backend changes, so it can be added in a later iteration without reopening this plan.

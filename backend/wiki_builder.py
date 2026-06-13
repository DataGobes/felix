"""Felix native LLM-wiki builder.

Pure functions (extraction parsing, dedup, planning, lint) plus a
`run_wiki_build` orchestrator that drives the extract -> plan -> write -> lint
pipeline. The LLM and embedding clients are injected so tests can stub them.
"""
from __future__ import annotations

import json
import math
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
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
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


# --------------------------------------------------------------------------
# Entity / relationship extraction
# --------------------------------------------------------------------------

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


# --------------------------------------------------------------------------
# Page-set planner
# --------------------------------------------------------------------------

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


# --------------------------------------------------------------------------
# Page-writing helpers
# --------------------------------------------------------------------------

_PAGE_SYSTEM = """You are writing one page of a structured knowledge wiki built \
from a document corpus. Write clear, factual Markdown.

Hard rules:
- Cite EVERY factual claim with [Felix:chunk:N] using the chunk markers provided.
- Link related wiki pages with [[slug]] using the provided link slugs.
- Start directly with a short intro paragraph, then use ## headings.
- Do NOT invent facts not present in the supplied chunks.
- Do NOT write YAML frontmatter; it is added automatically.
- Be concise; flag contradictions or uncertainty explicitly."""


def render_frontmatter(spec: PageSpec, sources: list[str], refs: Optional[list[int]] = None) -> str:
    ref_ids = refs if refs is not None else spec.related_chunk_ids
    refs_str = ", ".join(f"chunk:{c}" for c in ref_ids)
    src = ", ".join(sources)
    return (
        "---\n"
        f"title: {spec.title}\n"
        f"type: {spec.type}\n"
        f"sources: [{src}]\n"
        f"felix_refs: [{refs_str}]\n"
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


# --------------------------------------------------------------------------
# Lint + assembly helpers
# --------------------------------------------------------------------------

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


# --------------------------------------------------------------------------
# Real client adapters (injected into run_wiki_build from search.py)
# --------------------------------------------------------------------------

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


# --------------------------------------------------------------------------
# Pipeline stages
# --------------------------------------------------------------------------

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
        # Skip zero-evidence entity/concept pages rather than letting the LLM hallucinate.
        if not relevant and spec.type in ("entity", "concept"):
            continue
        link_titles = {slug: title_by_slug.get(slug, slug) for slug in spec.links}
        system, user = build_page_prompt(spec, relevant, link_titles)
        body = await llm.complete(system, user)
        body_refs = extract_felix_refs(body)
        sources = sorted({chunk_by_id[c].document_id for c in body_refs if c in chunk_by_id})
        frontmatter = render_frontmatter(spec, sources=[f"doc:{d}" for d in sources] or ["corpus"], refs=body_refs)
        links = sorted(set(spec.links) | set(extract_wiki_links(body)))
        written.append({
            "slug": spec.slug,
            "title": spec.title,
            "type": spec.type,
            "content_md": f"{frontmatter}\n\n{body}",
            "felix_refs": body_refs,
            "entity_name": spec.entity_name,
            "links": links,
        })
    return written


# --------------------------------------------------------------------------
# asyncpg DB helpers
# --------------------------------------------------------------------------

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

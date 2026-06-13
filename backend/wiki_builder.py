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

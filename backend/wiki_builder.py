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

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

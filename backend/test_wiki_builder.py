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


def test_extract_json_fenced_with_nested_objects():
    text = '```json\n{"entities": [{"name": "x", "chunk_ids": [1]}], "relationships": []}\n```'
    assert wb.extract_json(text) == {"entities": [{"name": "x", "chunk_ids": [1]}], "relationships": []}


def test_cosine_zero_norm_returns_zero():
    assert wb.cosine([0.0, 0.0], [1.0, 0.0]) == 0.0


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


async def test_write_stage_frontmatter_uses_body_citations():
    # overview has related_chunk_ids=[] but the body cites chunk:1 -> frontmatter must show it.
    chunks = [wb.ChunkRow(chunk_id=1, document_id=1, content="x")]
    specs = [wb.PageSpec(slug="overview", title="Overview", type="overview", related_chunk_ids=[])]
    written = await wb.run_write_stage(specs, chunks, ScriptedLLM())
    ov = next(w for w in written if w["slug"] == "overview")
    assert "felix_refs: [chunk:1]" in ov["content_md"]
    assert ov["felix_refs"] == [1]


async def test_write_stage_skips_zero_evidence_entity_page():
    chunks = [wb.ChunkRow(chunk_id=1, document_id=1, content="x")]
    specs = [wb.PageSpec(slug="ghost", title="Ghost", type="entity",
                         entity_name="Ghost", related_chunk_ids=[999])]  # 999 absent
    written = await wb.run_write_stage(specs, chunks, ScriptedLLM())
    assert all(w["slug"] != "ghost" for w in written)

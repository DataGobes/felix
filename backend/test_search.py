"""Tests for the RAG Search API (search.py).

All tests use mocked DB and OpenAI to run without external services.
"""

import json
from unittest.mock import MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from conftest import FAKE_EMBEDDING, MockConnection, MockPool, make_mock_pool

pytestmark = pytest.mark.asyncio


# ── Health & root ─────────────────────────────────────────────────────────


async def test_root(client):
    resp = await client.get("/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "embedding_model" in data


async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert data["database"] == "connected"


# ── Stats ─────────────────────────────────────────────────────────────────


async def test_stats_returns_all_keys(client_with_data):
    # fetchval is called 10 times in /stats — supply values in order
    stats_vals = [
        4,      # documents
        100,    # chunks
        100,    # embeddings
        20,     # pages
        500,    # layout_elements
        300,    # chunk_element_links
        50000,  # total_tokens
        10,     # images
        8,      # unique_images
        20,     # chunk_image_links
        5,      # tables
        5,      # unique_tables
        7,      # chunk_table_links
    ]
    client = await client_with_data({"fetchval": stats_vals})
    resp = await client.get("/stats")
    assert resp.status_code == 200
    data = resp.json()

    expected_keys = {
        "documents", "chunks", "embeddings", "pages", "layout_elements",
        "chunk_element_links", "total_tokens", "images", "unique_images",
        "chunk_image_links", "tables", "unique_tables", "chunk_table_links",
        "embedding_model",
    }
    assert expected_keys == set(data.keys())
    assert data["documents"] == 4
    assert data["embedding_model"] == "text-embedding-3-small"


# ── Documents ─────────────────────────────────────────────────────────────


async def test_list_documents(client_with_data):
    rows = [
        {"id": 1, "path": "test.pdf", "sha256": "abc123", "ingested_at": "2026-01-01T00:00:00+00:00",
         "file_size": 1024, "metadata": "{}", "chunk_count": 10},
    ]
    client = await client_with_data({"fetch": rows})
    resp = await client.get("/documents")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["documents"][0]["path"] == "test.pdf"


async def test_list_documents_empty(client_with_data):
    client = await client_with_data({"fetch": []})
    resp = await client.get("/documents")
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


# ── Chunks ────────────────────────────────────────────────────────────────


async def test_get_chunk_found(client_with_data):
    row = {
        "chunk_id": 42, "content": "Hello world", "document_id": 1,
        "document_path": "doc.pdf", "chunk_index": 0, "token_count": 5,
        "char_count": 11, "headings": ["Introduction"], "metadata": {},
    }
    client = await client_with_data({"fetchrow": row})
    resp = await client.get("/chunks/42")
    assert resp.status_code == 200
    data = resp.json()
    assert data["chunk_id"] == 42
    assert data["content"] == "Hello world"
    assert data["headings"] == ["Introduction"]


async def test_get_chunk_not_found(client_with_data):
    client = await client_with_data({"fetchrow": None})
    resp = await client.get("/chunks/999")
    assert resp.status_code == 404


# ── Search ────────────────────────────────────────────────────────────────


async def test_search_returns_results(client_with_data):
    rows = [
        {"chunk_id": 1, "content": "relevant text", "chunk_index": 0,
         "token_count": 10, "headings": ["Intro"], "document_path": "doc.pdf",
         "similarity": 0.95},
    ]
    client = await client_with_data({"fetch": rows})
    resp = await client.post("/search", json={"query": "test query", "top_k": 3})
    assert resp.status_code == 200
    data = resp.json()
    assert data["query"] == "test query"
    assert data["total_results"] == 1
    assert data["results"][0]["similarity"] == 0.95
    assert data["results"][0]["document_path"] == "doc.pdf"


async def test_search_empty_results(client_with_data):
    client = await client_with_data({"fetch": []})
    resp = await client.post("/search", json={"query": "nothing", "top_k": 5})
    assert resp.status_code == 200
    assert resp.json()["total_results"] == 0


async def test_search_validation_rejects_empty_query(client):
    resp = await client.post("/search", json={"query": "", "top_k": 5})
    assert resp.status_code == 422


async def test_search_validation_rejects_large_top_k(client):
    resp = await client.post("/search", json={"query": "test", "top_k": 100})
    assert resp.status_code == 422


async def test_search_validation_rejects_negative_threshold(client):
    resp = await client.post("/search", json={"query": "test", "threshold": -0.5})
    assert resp.status_code == 422


# ── Layout: pages ─────────────────────────────────────────────────────────


async def test_get_document_pages(client_with_data):
    rows = [
        {"page_id": 1, "page_number": 1, "width": 612.0, "height": 792.0, "element_count": 10},
        {"page_id": 2, "page_number": 2, "width": 612.0, "height": 792.0, "element_count": 15},
    ]
    client = await client_with_data({"fetch": rows})
    resp = await client.get("/documents/1/pages")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["page_number"] == 1
    assert data[1]["element_count"] == 15


async def test_get_document_pages_not_found(client_with_data):
    """Empty fetch + fetchval returning None → 404."""
    import search as search_module

    # Custom connection: fetch returns [], fetchval returns None (doc not found)
    conn = MockConnection()
    # Override methods for this specific test
    call_count = {"n": 0}
    original_fetch = conn.fetch

    async def _fetch(query, *args):
        return []

    async def _fetchval(query, *args):
        return None  # document doesn't exist

    conn.fetch = _fetch
    conn.fetchval = _fetchval

    pool = MockPool(conn)
    mock_openai = MagicMock()
    search_module.db_pool = pool
    search_module.openai_client = mock_openai

    from httpx import ASGITransport, AsyncClient
    transport = ASGITransport(app=search_module.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/documents/999/pages")
    assert resp.status_code == 404

    search_module.db_pool = None
    search_module.openai_client = None


# ── Layout: structure ─────────────────────────────────────────────────────


async def test_get_document_structure(client_with_data):
    """Mock: fetchval returns doc id, fetch returns headings."""
    import search as search_module

    conn = MockConnection()
    calls = {"n": 0}

    async def _fetchval(query, *args):
        return 1  # document exists

    async def _fetch(query, *args):
        return [
            {"reading_order": 1, "page_number": 1, "heading_level": 1,
             "heading_text": "Introduction", "self_ref": "#/texts/0"},
            {"reading_order": 5, "page_number": 3, "heading_level": 2,
             "heading_text": "Background", "self_ref": "#/texts/4"},
        ]

    conn.fetchval = _fetchval
    conn.fetch = _fetch

    pool = MockPool(conn)
    mock_openai = MagicMock()
    search_module.db_pool = pool
    search_module.openai_client = mock_openai

    transport = ASGITransport(app=search_module.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/documents/1/structure")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["heading_text"] == "Introduction"
    assert data[1]["heading_level"] == 2

    search_module.db_pool = None
    search_module.openai_client = None


async def test_get_document_structure_not_found(client_with_data):
    import search as search_module

    conn = MockConnection()
    conn.fetchval = AsyncMock_returning(None)

    pool = MockPool(conn)
    search_module.db_pool = pool
    search_module.openai_client = MagicMock()

    transport = ASGITransport(app=search_module.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/documents/999/structure")
    assert resp.status_code == 404

    search_module.db_pool = None
    search_module.openai_client = None


# ── Layout: page elements ─────────────────────────────────────────────────


async def test_get_page_elements(client_with_data):
    import search as search_module

    conn = MockConnection()

    async def _fetchval(query, *args):
        return 1  # page exists

    async def _fetch(query, *args):
        return [
            {"element_id": 10, "element_type": "text", "content_layer": "body",
             "reading_order": 0, "page_number": 1,
             "bbox_left": 72.0, "bbox_top": 700.0, "bbox_right": 540.0, "bbox_bottom": 650.0,
             "text_preview": "Hello world", "heading_level": None,
             "group_label": None, "children_count": 0},
        ]

    conn.fetchval = _fetchval
    conn.fetch = _fetch

    pool = MockPool(conn)
    search_module.db_pool = pool
    search_module.openai_client = MagicMock()

    transport = ASGITransport(app=search_module.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/pages/1/elements")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["element_type"] == "text"
    assert data[0]["bbox_left"] == 72.0

    search_module.db_pool = None
    search_module.openai_client = None


async def test_get_page_elements_with_type_filter(client_with_data):
    import search as search_module

    conn = MockConnection()

    async def _fetchval(query, *args):
        return 1

    async def _fetch(query, *args):
        # Verify the type filter is in the query
        assert "element_type" in query
        return []

    conn.fetchval = _fetchval
    conn.fetch = _fetch

    pool = MockPool(conn)
    search_module.db_pool = pool
    search_module.openai_client = MagicMock()

    transport = ASGITransport(app=search_module.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/pages/1/elements?element_type=section_header")
    assert resp.status_code == 200

    search_module.db_pool = None
    search_module.openai_client = None


async def test_get_page_elements_not_found(client_with_data):
    import search as search_module

    conn = MockConnection()
    conn.fetchval = AsyncMock_returning(None)

    pool = MockPool(conn)
    search_module.db_pool = pool
    search_module.openai_client = MagicMock()

    transport = ASGITransport(app=search_module.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/pages/999/elements")
    assert resp.status_code == 404

    search_module.db_pool = None
    search_module.openai_client = None


# ── Layout: chunk elements ────────────────────────────────────────────────


async def test_get_chunk_elements(client_with_data):
    import search as search_module

    conn = MockConnection()

    async def _fetchval(query, *args):
        return 1  # chunk exists

    async def _fetch(query, *args):
        return [
            {"element_id": 20, "element_type": "text", "content_layer": "body",
             "reading_order": 5, "page_number": 2,
             "bbox_left": 72.0, "bbox_top": 600.0, "bbox_right": 540.0, "bbox_bottom": 550.0,
             "text_preview": "chunk source element", "heading_level": None,
             "group_label": None, "children_count": 0},
        ]

    conn.fetchval = _fetchval
    conn.fetch = _fetch

    pool = MockPool(conn)
    search_module.db_pool = pool
    search_module.openai_client = MagicMock()

    transport = ASGITransport(app=search_module.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/chunks/1/elements")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["element_type"] == "text"

    search_module.db_pool = None
    search_module.openai_client = None


async def test_get_chunk_elements_not_found(client_with_data):
    import search as search_module

    conn = MockConnection()
    conn.fetchval = AsyncMock_returning(None)

    pool = MockPool(conn)
    search_module.db_pool = pool
    search_module.openai_client = MagicMock()

    transport = ASGITransport(app=search_module.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/chunks/999/elements")
    assert resp.status_code == 404

    search_module.db_pool = None
    search_module.openai_client = None


# ── Elements search ───────────────────────────────────────────────────────


async def test_elements_search(client_with_data):
    elements = [
        {"element_id": 30, "element_type": "section_header", "content_layer": "body",
         "reading_order": 1, "page_number": 1,
         "bbox_left": 72.0, "bbox_top": 700.0, "bbox_right": 300.0, "bbox_bottom": 680.0,
         "text_preview": "Introduction", "heading_level": 1,
         "group_label": None, "children_count": 0},
    ]
    client = await client_with_data({"fetch": elements})
    resp = await client.get("/elements/search?document_id=1&element_type=section_header&limit=10")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["element_type"] == "section_header"


async def test_elements_search_with_page_range(client_with_data):
    client = await client_with_data({"fetch": []})
    resp = await client.get("/elements/search?document_id=1&page_from=5&page_to=10")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_elements_search_requires_document_id(client):
    resp = await client.get("/elements/search")
    assert resp.status_code == 422


# ── Image endpoints ───────────────────────────────────────────────────────


async def test_image_duplicates_empty(client_with_data):
    client = await client_with_data({"fetch": []})
    resp = await client.get("/images/duplicates")
    assert resp.status_code == 200
    data = resp.json()
    assert data["duplicates"] == []
    assert data["total_groups"] == 0


async def test_get_image_not_found(client_with_data):
    client = await client_with_data({"fetchrow": None})
    resp = await client.get("/images/999")
    assert resp.status_code == 404


async def test_get_image_found(client_with_data):
    row = {
        "image_id": 1, "file_path": "1/img_0001.png", "file_size": 1024,
        "mime_type": "image/png", "width": 800, "height": 600, "page_number": 3,
        "bbox_left": 72.0, "bbox_top": 500.0, "bbox_right": 400.0, "bbox_bottom": 300.0,
        "caption": "Figure 1", "label": "picture", "image_index": 0,
        "phash": "abc123", "sha256": "def456",
        "extracted_at": "2026-01-01T00:00:00+00:00", "metadata": "{}",
        "document_path": "doc.pdf", "document_id": 1,
    }
    client = await client_with_data({"fetchrow": row})
    resp = await client.get("/images/1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["image_id"] == 1
    assert data["caption"] == "Figure 1"


# ── Table endpoints ───────────────────────────────────────────────────────


async def test_table_duplicates_empty(client_with_data):
    client = await client_with_data({"fetch": []})
    resp = await client.get("/tables/duplicates")
    assert resp.status_code == 200
    assert resp.json()["total_groups"] == 0


async def test_get_table_not_found(client_with_data):
    client = await client_with_data({"fetchrow": None})
    resp = await client.get("/tables/999")
    assert resp.status_code == 404


async def test_get_table_found(client_with_data):
    row = {
        "table_id": 1, "table_index": 0, "num_rows": 5, "num_cols": 3,
        "page_number": 10,
        "bbox_left": 72.0, "bbox_top": 500.0, "bbox_right": 540.0, "bbox_bottom": 300.0,
        "caption": "Table 1", "label": "table",
        "content_markdown": "| A | B | C |", "content_html": "<table>...</table>",
        "content_text": "A, B = 1", "sha256": "abc123",
        "extracted_at": "2026-01-01T00:00:00+00:00", "metadata": "{}",
        "document_path": "doc.pdf", "document_id": 1,
    }
    client = await client_with_data({"fetchrow": row})
    resp = await client.get("/tables/1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["table_id"] == 1
    assert data["content_markdown"] == "| A | B | C |"


async def test_get_chunk_images(client_with_data):
    client = await client_with_data({"fetch": []})
    resp = await client.get("/chunks/1/images")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_get_chunk_tables(client_with_data):
    client = await client_with_data({"fetch": []})
    resp = await client.get("/chunks/1/tables")
    assert resp.status_code == 200
    assert resp.json() == []


# ── GET /images/{image_id}/file ───────────────────────────────────────────


async def test_get_image_file_not_found_in_db(client_with_data):
    client = await client_with_data({"fetchrow": None})
    resp = await client.get("/images/999/file")
    assert resp.status_code == 404


async def test_get_image_file_serves_png(client_with_data, tmp_path):
    """When the image exists on disk, serve it as a file response."""
    import search as search_module

    # Create a fake image file
    img_dir = tmp_path / "19"
    img_dir.mkdir()
    img_file = img_dir / "img_0000.png"
    img_file.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)  # minimal PNG header

    conn = MockConnection()
    conn.fetchrow = AsyncMock_returning({"file_path": "19/img_0000.png", "mime_type": "image/png"})

    pool = MockPool(conn)
    search_module.db_pool = pool
    search_module.openai_client = MagicMock()

    # Point IMAGES_PATH to our temp dir
    original_path = search_module.IMAGES_PATH
    search_module.IMAGES_PATH = tmp_path

    transport = ASGITransport(app=search_module.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/images/119/file")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"
    assert len(resp.content) > 0

    search_module.IMAGES_PATH = original_path
    search_module.db_pool = None
    search_module.openai_client = None


# ── GET /chunks/{chunk_id} — JSONB metadata as string ────────────────────


async def test_get_chunk_with_string_metadata(client_with_data):
    """Regression: asyncpg may return JSONB as a string, not a dict."""
    row = {
        "chunk_id": 55, "content": "text", "document_id": 1,
        "document_path": "doc.pdf", "chunk_index": 3, "token_count": 5,
        "char_count": 4, "headings": [],
        "metadata": '{"element_refs": ["#/texts/40"], "page_numbers": [21]}',
    }
    client = await client_with_data({"fetchrow": row})
    resp = await client.get("/chunks/55")
    assert resp.status_code == 200
    data = resp.json()
    assert data["chunk_id"] == 55
    assert data["metadata"]["element_refs"] == ["#/texts/40"]
    assert data["metadata"]["page_numbers"] == [21]


async def test_get_chunk_with_null_metadata(client_with_data):
    """metadata can be None/null in edge cases."""
    row = {
        "chunk_id": 56, "content": "text", "document_id": 1,
        "document_path": "doc.pdf", "chunk_index": 0, "token_count": 2,
        "char_count": 4, "headings": None, "metadata": None,
    }
    client = await client_with_data({"fetchrow": row})
    resp = await client.get("/chunks/56")
    assert resp.status_code == 200
    assert resp.json()["metadata"] == {}


# ── GET /documents/{document_id}/chunks ──────────────────────────────────


async def test_get_document_chunks(client_with_data):
    import search as search_module

    conn = MockConnection()
    call_count = 0

    async def _fetchval(query, *args):
        nonlocal call_count
        call_count += 1
        return 1  # document exists

    async def _fetch(query, *args):
        return [
            {"chunk_id": 10, "content": "First chunk", "chunk_index": 0,
             "token_count": 5, "char_count": 11, "headings": ["Intro"],
             "metadata": '{}', "page_number": 1},
            {"chunk_id": 11, "content": "Second chunk", "chunk_index": 1,
             "token_count": 6, "char_count": 12, "headings": ["Intro"],
             "metadata": '{"element_refs": []}', "page_number": 1},
        ]

    conn.fetchval = _fetchval
    conn.fetch = _fetch

    pool = MockPool(conn)
    search_module.db_pool = pool
    search_module.openai_client = MagicMock()

    transport = ASGITransport(app=search_module.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/documents/1/chunks")
    assert resp.status_code == 200
    data = resp.json()
    assert data["document_id"] == 1
    assert data["total"] == 2
    assert data["chunks"][0]["chunk_id"] == 10
    assert data["chunks"][0]["content"] == "First chunk"
    assert data["chunks"][1]["page_number"] == 1

    search_module.db_pool = None
    search_module.openai_client = None


async def test_get_document_chunks_not_found(client_with_data):
    client = await client_with_data({"fetchval": [None]})
    resp = await client.get("/documents/999/chunks")
    assert resp.status_code == 404


# ── Elements with include_text ───────────────────────────────────────────


async def test_page_elements_with_include_text(client_with_data):
    import search as search_module

    conn = MockConnection()

    async def _fetchval(query, *args):
        return 1  # page exists

    async def _fetch(query, *args):
        return [
            {"element_id": 1, "element_type": "text", "content_layer": "body",
             "reading_order": 0, "page_number": 1,
             "bbox_left": 72.0, "bbox_top": 700.0, "bbox_right": 540.0, "bbox_bottom": 650.0,
             "text_preview": "This is a long paragraph that gets trunca...",
             "full_text": "This is a long paragraph that gets truncated at 200 chars but here you get the whole thing",
             "heading_level": None, "group_label": None, "children_count": 0},
        ]

    conn.fetchval = _fetchval
    conn.fetch = _fetch

    pool = MockPool(conn)
    search_module.db_pool = pool
    search_module.openai_client = MagicMock()

    transport = ASGITransport(app=search_module.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/pages/1/elements?include_text=true")
    assert resp.status_code == 200
    data = resp.json()
    assert data[0]["full_text"] is not None
    assert "whole thing" in data[0]["full_text"]

    search_module.db_pool = None
    search_module.openai_client = None


async def test_page_elements_without_include_text(client_with_data):
    """By default full_text is not included."""
    import search as search_module

    conn = MockConnection()

    async def _fetchval(query, *args):
        return 1

    async def _fetch(query, *args):
        return [
            {"element_id": 1, "element_type": "text", "content_layer": "body",
             "reading_order": 0, "page_number": 1,
             "bbox_left": None, "bbox_top": None, "bbox_right": None, "bbox_bottom": None,
             "text_preview": "preview only",
             "heading_level": None, "group_label": None, "children_count": 0},
        ]

    conn.fetchval = _fetchval
    conn.fetch = _fetch

    pool = MockPool(conn)
    search_module.db_pool = pool
    search_module.openai_client = MagicMock()

    transport = ASGITransport(app=search_module.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/pages/1/elements")
    assert resp.status_code == 200
    data = resp.json()
    assert data[0]["full_text"] is None
    assert data[0]["text_preview"] == "preview only"

    search_module.db_pool = None
    search_module.openai_client = None


# ── Helpers ───────────────────────────────────────────────────────────────


def AsyncMock_returning(value):
    """Create an async callable that always returns ``value``."""
    async def _mock(*args, **kwargs):
        return value
    return _mock

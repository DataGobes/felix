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

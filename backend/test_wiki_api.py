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
    client = await client_for({"fetchval": [1, None, 77]})  # index_id, no active job, then job_id
    resp = await client.post("/indexes/default/wiki/build")
    assert resp.status_code == 200
    assert resp.json()["job_id"] == 77
    assert resp.json()["status"] == "queued"


async def test_build_wiki_rejects_when_active(client_for):
    # index_id=1, then an active job id (5) -> 409, no enqueue.
    client = await client_for({"fetchval": [1, 5]})
    resp = await client.post("/indexes/default/wiki/build")
    assert resp.status_code == 409


async def test_wiki_stream_emits_event_and_closes(client_for):
    # A terminal-status job makes the SSE generator emit one event then return,
    # so the stream closes cleanly (an in-progress status would poll forever and
    # hang the ASGI test transport, which cannot tear down an infinite generator).
    client = await client_for({"fetchrow": {"id": 1, "status": "completed", "progress": {},
                                            "error_message": None}, "fetchval": [1]})
    async with client.stream("GET", "/indexes/default/wiki/stream") as resp:
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        lines = [line async for line in resp.aiter_lines()]
    assert any(line.startswith("data:") for line in lines)

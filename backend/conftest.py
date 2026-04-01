"""Shared fixtures for RAG test suite."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient


@pytest.fixture(autouse=True)
def _set_env(monkeypatch):
    """Set required environment variables before importing the app."""
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://test.openai.azure.com")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("POSTGRES_PASSWORD", "test-password")
    monkeypatch.setenv("POSTGRES_HOST", "localhost")
    monkeypatch.setenv("AZURE_OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")


# ---------------------------------------------------------------------------
# Mock DB pool: asyncpg-compatible async context manager
# ---------------------------------------------------------------------------

class MockConnection:
    """Mimics an asyncpg connection with fetch/fetchrow/fetchval."""

    def __init__(self, responses: dict | None = None):
        self._responses = responses or {}
        self._call_log: list[tuple[str, tuple]] = []

    async def fetch(self, query: str, *args):
        self._call_log.append(("fetch", (query, *args)))
        return self._responses.get("fetch", [])

    async def fetchrow(self, query: str, *args):
        self._call_log.append(("fetchrow", (query, *args)))
        return self._responses.get("fetchrow", None)

    async def fetchval(self, query: str, *args):
        self._call_log.append(("fetchval", (query, *args)))
        vals = self._responses.get("fetchval", [])
        if isinstance(vals, list) and vals:
            return vals.pop(0)
        return vals


class MockPool:
    """Mimics asyncpg.Pool with an acquire() context manager."""

    def __init__(self, conn: MockConnection):
        self._conn = conn

    def acquire(self):
        return _AcquireCtx(self._conn)


class _AcquireCtx:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *exc):
        pass


def make_mock_pool(responses: dict | None = None) -> MockPool:
    """Create a MockPool that returns pre-configured responses."""
    return MockPool(MockConnection(responses or {}))


# ---------------------------------------------------------------------------
# App-level fixtures
# ---------------------------------------------------------------------------

FAKE_EMBEDDING = [0.1] * 1536


@pytest_asyncio.fixture
async def client():
    """Async test client with mocked DB pool and OpenAI client.

    By default the mock pool returns empty results. Individual tests
    override via ``mock_pool_responses`` if they need specific data.
    """
    import search as search_module

    pool = make_mock_pool({
        "fetchval": [1],  # SELECT 1 health check
    })

    mock_openai = MagicMock()
    mock_embedding_resp = MagicMock()
    mock_embedding_resp.data = [MagicMock(embedding=FAKE_EMBEDDING)]
    mock_openai.embeddings.create.return_value = mock_embedding_resp

    # Patch module globals
    search_module.db_pool = pool
    search_module.openai_client = mock_openai

    transport = ASGITransport(app=search_module.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    # Cleanup
    search_module.db_pool = None
    search_module.openai_client = None


@pytest_asyncio.fixture
async def client_with_data():
    """Factory fixture: returns an async client backed by a pool that serves
    the provided response dict.

    Usage:
        async def test_something(client_with_data):
            client = await client_with_data({"fetch": [...], "fetchval": [...]})
            resp = await client.get("/stats")
    """
    import search as search_module

    clients = []

    async def _factory(responses: dict):
        pool = make_mock_pool(responses)

        mock_openai = MagicMock()
        mock_embedding_resp = MagicMock()
        mock_embedding_resp.data = [MagicMock(embedding=FAKE_EMBEDDING)]
        mock_openai.embeddings.create.return_value = mock_embedding_resp

        search_module.db_pool = pool
        search_module.openai_client = mock_openai

        transport = ASGITransport(app=search_module.app)
        ac = AsyncClient(transport=transport, base_url="http://test")
        clients.append(ac)
        return ac

    yield _factory

    for ac in clients:
        await ac.aclose()
    search_module.db_pool = None
    search_module.openai_client = None

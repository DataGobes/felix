#!/usr/bin/env python3
"""
RAG Search API

FastAPI service for semantic search over ingested documents.
Exposes POST /search endpoint for querying the vector database.
"""

import os
import structlog
from contextlib import asynccontextmanager
from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from typing import Optional, List
from pathlib import Path
import hashlib
import time
import json
import asyncio
from enum import Enum
from fastapi.responses import FileResponse
from starlette.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import asyncpg
from openai import AzureOpenAI
import wiki_builder as wiki

# Configure logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger("rag-search")

# Configuration from environment
DB_HOST = os.getenv("POSTGRES_HOST", "rag-postgres")
DB_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
DB_USER = os.getenv("POSTGRES_USER", "raguser")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD")
DB_NAME = os.getenv("POSTGRES_DB", "ragdb")

# Azure OpenAI config
AZURE_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-01")
AZURE_EMBEDDING_MODEL = os.getenv("AZURE_OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")

# Image storage path (read-only mount)
IMAGES_PATH = Path(os.getenv("IMAGES_PATH", "/images"))
INGEST_PATH = Path(os.getenv("INGEST_PATH", "/ingest"))
ALLOWED_EXTENSIONS = {".pdf", ".txt", ".md", ".docx", ".html", ".xlsx", ".pptx"}

# Database pool
db_pool: Optional[asyncpg.Pool] = None

# Azure OpenAI client
openai_client: Optional[AzureOpenAI] = None


# ── Search mode enum ─────────────────────────────────────────────
class SearchMode(str, Enum):
    vector = "vector"
    keyword = "keyword"
    hybrid = "hybrid"


# Pydantic models
class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=10000, description="Search query text")
    top_k: int = Field(default=5, ge=1, le=50, description="Number of results to return")
    threshold: float = Field(default=0.0, ge=0.0, le=1.0,
                             description="Minimum similarity threshold (0-1)")
    include_images: bool = Field(default=False, description="Include related images in results")
    include_tables: bool = Field(default=False, description="Include related tables in results")
    search_mode: SearchMode = Field(default=SearchMode.vector, description="Search mode: vector, keyword, or hybrid")
    document_ids: Optional[List[int]] = Field(default=None, description="Filter results to specific document IDs")
    index_slug: Optional[str] = Field(default=None, description="Filter search to a specific index")


class IndexCreate(BaseModel):
    slug: str = Field(..., min_length=1, max_length=100, pattern=r"^[a-z0-9][a-z0-9-]*$")
    display_name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None


class ImageResult(BaseModel):
    image_id: int
    file_path: str
    page_number: Optional[int] = None
    caption: Optional[str] = None
    label: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    relationship_type: str
    document_path: Optional[str] = None


class TableResult(BaseModel):
    table_id: int
    num_rows: int
    num_cols: int
    page_number: Optional[int] = None
    caption: Optional[str] = None
    content_markdown: str
    relationship_type: str
    document_path: Optional[str] = None


class SearchResult(BaseModel):
    chunk_id: int
    content: str
    document_path: str
    similarity: float
    chunk_index: Optional[int] = None
    token_count: Optional[int] = None
    headings: Optional[List[str]] = None
    images: Optional[List[ImageResult]] = None
    tables: Optional[List[TableResult]] = None


class ChunkResponse(BaseModel):
    chunk_id: int
    content: str
    document_id: int
    document_path: str
    chunk_index: int
    token_count: Optional[int] = None
    char_count: Optional[int] = None
    headings: Optional[List[str]] = None
    metadata: dict = {}


class SearchResponse(BaseModel):
    query: str
    results: List[SearchResult]
    total_results: int
    embedding_model: Optional[str] = None
    search_mode: str = "vector"


class HealthResponse(BaseModel):
    status: str
    database: str
    embedding_model: str


class PageInfo(BaseModel):
    page_id: int
    page_number: int
    width: float
    height: float
    element_count: int


class LayoutElement(BaseModel):
    element_id: int
    element_type: str
    content_layer: str
    reading_order: int
    page_number: Optional[int] = None
    bbox_left: Optional[float] = None
    bbox_top: Optional[float] = None
    bbox_right: Optional[float] = None
    bbox_bottom: Optional[float] = None
    text_preview: Optional[str] = None
    full_text: Optional[str] = None
    heading_level: Optional[int] = None
    group_label: Optional[str] = None
    children_count: int = 0
    metadata: dict | None = None


class StructureHeading(BaseModel):
    reading_order: int
    page_number: Optional[int] = None
    heading_level: Optional[int] = None
    heading_text: Optional[str] = None
    self_ref: str


async def get_db_pool() -> asyncpg.Pool:
    """Get or create database connection pool."""
    global db_pool
    if db_pool is None:
        db_pool = await asyncpg.create_pool(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
            min_size=2,
            max_size=10
        )
    return db_pool


def get_openai_client() -> AzureOpenAI:
    """Get or create Azure OpenAI client."""
    global openai_client
    if openai_client is None:
        openai_client = AzureOpenAI(
            azure_endpoint=AZURE_ENDPOINT,
            api_key=AZURE_API_KEY,
            api_version=AZURE_API_VERSION
        )
    return openai_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan."""
    logger.info("search_api_starting")

    missing = []
    if not AZURE_ENDPOINT:
        missing.append("AZURE_OPENAI_ENDPOINT")
    if not AZURE_API_KEY:
        missing.append("AZURE_OPENAI_API_KEY")
    if not DB_PASSWORD:
        missing.append("POSTGRES_PASSWORD")

    if missing:
        logger.error("missing_configuration", variables=missing)
        raise RuntimeError(f"Missing configuration: {', '.join(missing)}")

    await get_db_pool()
    logger.info("database_connected", host=DB_HOST, database=DB_NAME)

    client = get_openai_client()
    logger.info("openai_client_ready", endpoint=AZURE_ENDPOINT, model=AZURE_EMBEDDING_MODEL)

    # Reap orphaned wiki jobs: a non-terminal job at startup means the worker
    # died mid-build; mark it failed so it doesn't block new builds or hang the UI.
    try:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE wiki_jobs SET status = 'failed', "
                "error_message = 'interrupted by restart', completed_at = NOW() "
                "WHERE status NOT IN ('completed', 'failed')")
    except Exception as e:
        logger.warning("wiki_job_reap_failed", error=str(e))

    yield

    logger.info("search_api_shutting_down")
    if db_pool:
        await db_pool.close()


# Create FastAPI app
app = FastAPI(
    title="RAG Search API",
    description="Semantic search over ingested documents using pgvector and Azure OpenAI embeddings",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Helpers ───────────────────────────────────────────────────────────────


async def generate_embedding(text: str) -> List[float]:
    """Generate embedding for query text."""
    client = get_openai_client()
    try:
        response = client.embeddings.create(
            model=AZURE_EMBEDDING_MODEL,
            input=text
        )
        return response.data[0].embedding
    except Exception as e:
        logger.error("embedding_generation_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to generate embedding: {str(e)}")


async def search_similar_chunks(
    embedding: List[float],
    top_k: int = 5,
    threshold: float = 0.0,
    document_ids: Optional[List[int]] = None,
) -> List[dict]:
    """Search for similar chunks using cosine similarity."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        doc_filter = ""
        params = [json.dumps(embedding), threshold, top_k]
        if document_ids:
            doc_filter = "AND c.document_id = ANY($4::int[])"
            params.append(document_ids)

        rows = await conn.fetch(
            f"""
            SELECT
                c.id AS chunk_id, c.content, c.chunk_index, c.token_count,
                c.headings, d.path AS document_path,
                1 - (e.embedding <=> $1::vector) AS similarity
            FROM embeddings e
            JOIN chunks c ON c.id = e.chunk_id
            JOIN documents d ON d.id = c.document_id
            WHERE 1 - (e.embedding <=> $1::vector) > $2
              {doc_filter}
            ORDER BY e.embedding <=> $1::vector
            LIMIT $3
            """,
            *params,
        )
        return [dict(row) for row in rows]


async def search_fulltext_chunks(
    query: str,
    top_k: int = 5,
    document_ids: Optional[List[int]] = None,
) -> List[dict]:
    """Full-text search on chunks using tsvector + ts_rank_cd."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        doc_filter = ""
        params = [query, top_k]
        if document_ids:
            doc_filter = "AND c.document_id = ANY($3::int[])"
            params.append(document_ids)

        rows = await conn.fetch(
            f"""
            SELECT
                c.id AS chunk_id, c.content, c.chunk_index, c.token_count,
                c.headings, d.path AS document_path,
                ts_rank_cd(c.content_tsv, plainto_tsquery('english', $1)) AS similarity
            FROM chunks c
            JOIN documents d ON d.id = c.document_id
            WHERE c.content_tsv @@ plainto_tsquery('english', $1)
              {doc_filter}
            ORDER BY similarity DESC
            LIMIT $2
            """,
            *params,
        )
        return [dict(row) for row in rows]


def reciprocal_rank_fusion(
    vector_results: List[dict],
    keyword_results: List[dict],
    top_k: int = 5,
    k: int = 60,
) -> List[dict]:
    """Combine vector and keyword results using Reciprocal Rank Fusion."""
    scores: dict[int, float] = {}
    items: dict[int, dict] = {}

    for rank, result in enumerate(vector_results):
        cid = result["chunk_id"]
        scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank + 1)
        items[cid] = result

    for rank, result in enumerate(keyword_results):
        cid = result["chunk_id"]
        scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank + 1)
        if cid not in items:
            items[cid] = result

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]
    results = []
    for cid, rrf_score in ranked:
        item = dict(items[cid])
        item["similarity"] = round(rrf_score, 6)
        results.append(item)
    return results


async def get_chunks_images_batch(chunk_ids: List[int]) -> dict:
    """Batch-fetch images for multiple chunk_ids."""
    if not chunk_ids:
        return {}
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT ci.chunk_id,
                   i.id AS image_id, i.file_path, i.page_number,
                   i.caption, i.label, i.width, i.height,
                   ci.relationship_type,
                   d.path AS document_path
            FROM chunk_images ci
            JOIN images i ON i.id = ci.image_id
            JOIN documents d ON d.id = i.document_id
            WHERE ci.chunk_id = ANY($1)
            ORDER BY i.page_number, i.image_index
            """,
            chunk_ids,
        )
    result: dict = {}
    for row in rows:
        cid = row["chunk_id"]
        result.setdefault(cid, []).append(
            ImageResult(
                image_id=row["image_id"],
                file_path=row["file_path"],
                page_number=row["page_number"],
                caption=row["caption"],
                label=row["label"],
                width=row["width"],
                height=row["height"],
                relationship_type=row["relationship_type"],
                document_path=row["document_path"],
            )
        )
    return result


async def get_chunks_tables_batch(chunk_ids: List[int]) -> dict:
    """Batch-fetch tables for multiple chunk_ids."""
    if not chunk_ids:
        return {}
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT ct.chunk_id,
                   t.id AS table_id, t.num_rows, t.num_cols,
                   t.page_number, t.caption, t.content_markdown,
                   ct.relationship_type,
                   d.path AS document_path
            FROM chunk_tables ct
            JOIN tables t ON t.id = ct.table_id
            JOIN documents d ON d.id = t.document_id
            WHERE ct.chunk_id = ANY($1)
            ORDER BY t.page_number, t.table_index
            """,
            chunk_ids,
        )
    result: dict = {}
    for row in rows:
        cid = row["chunk_id"]
        result.setdefault(cid, []).append(
            TableResult(
                table_id=row["table_id"],
                num_rows=row["num_rows"],
                num_cols=row["num_cols"],
                page_number=row["page_number"],
                caption=row["caption"],
                content_markdown=row["content_markdown"],
                relationship_type=row["relationship_type"],
                document_path=row["document_path"],
            )
        )
    return result


# ── Health ────────────────────────────────────────────────────────────────


@app.get("/", response_model=HealthResponse)
async def root():
    return HealthResponse(
        status="ok",
        database=f"{DB_HOST}:{DB_PORT}/{DB_NAME}",
        embedding_model=AZURE_EMBEDDING_MODEL
    )


@app.get("/health", response_model=HealthResponse)
async def health():
    try:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        db_status = "connected"
    except Exception as e:
        logger.error("health_check_db_failed", error=str(e))
        raise HTTPException(status_code=503, detail="Database unavailable")

    return HealthResponse(
        status="healthy",
        database=db_status,
        embedding_model=AZURE_EMBEDDING_MODEL
    )


# ── Search ────────────────────────────────────────────────────────────────


@app.post("/search", response_model=SearchResponse)
async def search(request: SearchRequest):
    """Search for similar chunks using vector, keyword, or hybrid mode."""
    mode = request.search_mode
    logger.info("search_request",
               query=request.query[:100],
               top_k=request.top_k,
               threshold=request.threshold,
               search_mode=mode.value)

    try:
        if mode == SearchMode.keyword:
            results = await search_fulltext_chunks(
                query=request.query,
                top_k=request.top_k,
                document_ids=request.document_ids,
            )
        elif mode == SearchMode.hybrid:
            embedding = await generate_embedding(request.query)
            vector_results, keyword_results = await asyncio.gather(
                search_similar_chunks(
                    embedding=embedding,
                    top_k=request.top_k * 2,
                    threshold=request.threshold,
                    document_ids=request.document_ids,
                ),
                search_fulltext_chunks(
                    query=request.query,
                    top_k=request.top_k * 2,
                    document_ids=request.document_ids,
                ),
            )
            results = reciprocal_rank_fusion(
                vector_results, keyword_results, top_k=request.top_k
            )
        else:
            embedding = await generate_embedding(request.query)
            results = await search_similar_chunks(
                embedding=embedding,
                top_k=request.top_k,
                threshold=request.threshold,
                document_ids=request.document_ids,
            )

        chunk_ids = [r["chunk_id"] for r in results] if results else []
        images_by_chunk: dict = {}
        if request.include_images and chunk_ids:
            images_by_chunk = await get_chunks_images_batch(chunk_ids)
        tables_by_chunk: dict = {}
        if request.include_tables and chunk_ids:
            tables_by_chunk = await get_chunks_tables_batch(chunk_ids)

        search_results = []
        for r in results:
            search_results.append(SearchResult(
                chunk_id=r["chunk_id"],
                content=r["content"],
                document_path=r["document_path"],
                similarity=round(r["similarity"], 4),
                chunk_index=r.get("chunk_index"),
                token_count=r.get("token_count"),
                headings=r.get("headings"),
                images=images_by_chunk.get(r["chunk_id"]) or None,
                tables=tables_by_chunk.get(r["chunk_id"]) or None,
            ))

        logger.info("search_complete",
                   query=request.query[:100],
                   search_mode=mode.value,
                   results_found=len(search_results))

        return SearchResponse(
            query=request.query,
            results=search_results,
            total_results=len(search_results),
            embedding_model=AZURE_EMBEDDING_MODEL if mode != SearchMode.keyword else None,
            search_mode=mode.value,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("search_failed", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


# ── Documents ─────────────────────────────────────────────────────────────


@app.get("/documents")
async def list_documents(index_slug: Optional[str] = None):
    """List all ingested documents, optionally filtered by index."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        if index_slug:
            rows = await conn.fetch(
                """
                SELECT d.id, d.path, d.sha256, d.ingested_at, d.file_size, d.metadata,
                       COUNT(c.id) AS chunk_count, i.display_name AS index_name
                FROM documents d
                LEFT JOIN chunks c ON c.document_id = d.id
                LEFT JOIN indexes i ON i.id = d.index_id
                WHERE i.slug = $1
                GROUP BY d.id, i.display_name
                ORDER BY d.ingested_at DESC
                """,
                index_slug,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT d.id, d.path, d.sha256, d.ingested_at, d.file_size, d.metadata,
                       COUNT(c.id) AS chunk_count, i.display_name AS index_name
                FROM documents d
                LEFT JOIN chunks c ON c.document_id = d.id
                LEFT JOIN indexes i ON i.id = d.index_id
                GROUP BY d.id, i.display_name
                ORDER BY d.ingested_at DESC
                """
            )
        return {"documents": [dict(row) for row in rows], "total": len(rows)}


@app.get("/documents/{document_id}/chunks")
async def get_document_chunks(document_id: int):
    """List all chunks for a document, ordered by chunk_index."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        doc = await conn.fetchval("SELECT id FROM documents WHERE id = $1", document_id)
        if not doc:
            raise HTTPException(status_code=404, detail=f"Document {document_id} not found")

        rows = await conn.fetch(
            """
            SELECT
                c.id AS chunk_id, c.content, c.chunk_index, c.token_count,
                c.char_count, c.headings, c.metadata,
                (
                    SELECT DISTINCT le.page_number
                    FROM chunk_elements ce
                    JOIN layout_elements le ON le.id = ce.element_id
                    WHERE ce.chunk_id = c.id AND le.page_number IS NOT NULL
                    ORDER BY le.page_number
                    LIMIT 1
                ) AS page_number,
                ARRAY(
                    SELECT DISTINCT le2.page_number
                    FROM chunk_elements ce2
                    JOIN layout_elements le2 ON le2.id = ce2.element_id
                    WHERE ce2.chunk_id = c.id AND le2.page_number IS NOT NULL
                    ORDER BY le2.page_number
                ) AS page_numbers
            FROM chunks c
            WHERE c.document_id = $1
            ORDER BY c.chunk_index
            """,
            document_id,
        )

        chunks = []
        for row in rows:
            metadata = row.get("metadata") or {}
            if isinstance(metadata, str):
                metadata = json.loads(metadata)
            page_nums = row.get("page_numbers")
            chunks.append({
                "chunk_id": row["chunk_id"],
                "content": row["content"],
                "chunk_index": row["chunk_index"],
                "token_count": row["token_count"],
                "char_count": row["char_count"],
                "headings": row["headings"],
                "page_number": row.get("page_number"),
                "page_numbers": list(page_nums) if page_nums else [],
                "metadata": metadata or {},
            })
        return {"document_id": document_id, "chunks": chunks, "total": len(chunks)}


@app.get("/documents/{document_id}/detail")
async def get_document_detail(document_id: int):
    """Get full document detail including chunks, images, tables, and layout elements."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        doc = await conn.fetchrow(
            """
            SELECT d.id, d.path, d.sha256, d.ingested_at, d.file_size, d.metadata,
                   i.slug AS index_slug, i.display_name AS index_name
            FROM documents d
            LEFT JOIN indexes i ON i.id = d.index_id
            WHERE d.id = $1
            """,
            document_id,
        )
        if not doc:
            raise HTTPException(status_code=404, detail=f"Document {document_id} not found")

        chunks = await conn.fetch(
            """
            SELECT c.id, c.content, c.chunk_index, c.token_count, c.char_count,
                   c.headings, c.metadata,
                   ARRAY(
                       SELECT DISTINCT le.page_number
                       FROM chunk_elements ce
                       JOIN layout_elements le ON le.id = ce.element_id
                       WHERE ce.chunk_id = c.id AND le.page_number IS NOT NULL
                       ORDER BY le.page_number
                   ) AS page_numbers
            FROM chunks c WHERE c.document_id = $1 ORDER BY c.chunk_index
            """,
            document_id,
        )
        images = await conn.fetch(
            """
            SELECT id, page_number, file_path, caption, label, width, height,
                   image_index, phash, sha256, metadata
            FROM images WHERE document_id = $1 ORDER BY page_number, image_index
            """,
            document_id,
        )
        tables = await conn.fetch(
            """
            SELECT id, page_number, table_index, num_rows, num_cols, caption, label,
                   content_markdown, content_html, content_text, sha256, metadata
            FROM tables WHERE document_id = $1 ORDER BY page_number, table_index
            """,
            document_id,
        )
        pages = await conn.fetch(
            "SELECT id, page_number, width, height, element_count "
            "FROM pages WHERE document_id = $1 ORDER BY page_number",
            document_id,
        )
        elements = await conn.fetch(
            """
            SELECT le.id, le.page_number, le.element_type, le.content_layer,
                   le.reading_order,
                   le.bbox_left, le.bbox_top, le.bbox_right, le.bbox_bottom,
                   le.text_preview, le.heading_level, le.group_label,
                   le.children_count, le.metadata
            FROM layout_elements le
            WHERE le.document_id = $1
            ORDER BY le.page_number, le.reading_order
            """,
            document_id,
        )
        return {
            "document": dict(doc),
            "chunks": [dict(r) for r in chunks],
            "images": [dict(r) for r in images],
            "tables": [dict(r) for r in tables],
            "pages": [dict(r) for r in pages],
            "layout_elements": [dict(r) for r in elements],
        }




@app.delete("/documents/{document_id}")
async def delete_document(document_id: int):
    """Delete a document and all related data (cascades to chunks, embeddings, images, tables, etc)."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT id, path FROM documents WHERE id = $1", document_id)
        if not row:
            raise HTTPException(status_code=404, detail=f"Document {document_id} not found")
        await conn.execute("DELETE FROM documents WHERE id = $1", document_id)
        return {"status": "deleted", "document_id": document_id, "path": row["path"]}


@app.get("/documents/{document_id}/pages", response_model=List[PageInfo])
async def get_document_pages(document_id: int):
    """List all pages for a document."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id AS page_id, page_number, width, height, element_count
            FROM pages WHERE document_id = $1 ORDER BY page_number
            """,
            document_id,
        )
        if not rows:
            doc = await conn.fetchval("SELECT id FROM documents WHERE id = $1", document_id)
            if not doc:
                raise HTTPException(status_code=404, detail=f"Document {document_id} not found")
            return []
        return [PageInfo(**dict(r)) for r in rows]


@app.get("/documents/{document_id}/structure", response_model=List[StructureHeading])
async def get_document_structure(document_id: int):
    """Get document heading structure."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        doc = await conn.fetchval("SELECT id FROM documents WHERE id = $1", document_id)
        if not doc:
            raise HTTPException(status_code=404, detail=f"Document {document_id} not found")

        rows = await conn.fetch(
            """
            SELECT reading_order, page_number, heading_level, heading_text, self_ref
            FROM document_structure
            WHERE document_id = $1
            ORDER BY reading_order
            """,
            document_id,
        )
        return [StructureHeading(**dict(r)) for r in rows]


# ── Stats ─────────────────────────────────────────────────────────────────


@app.get("/stats")
async def get_stats():
    """Get pipeline statistics."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        doc_count = await conn.fetchval("SELECT COUNT(*) FROM documents")
        chunk_count = await conn.fetchval("SELECT COUNT(*) FROM chunks")
        embedding_count = await conn.fetchval("SELECT COUNT(*) FROM embeddings")
        page_count = await conn.fetchval("SELECT COUNT(*) FROM pages")
        element_count = await conn.fetchval("SELECT COUNT(*) FROM layout_elements")
        chunk_element_count = await conn.fetchval("SELECT COUNT(*) FROM chunk_elements")
        total_tokens = await conn.fetchval("SELECT COALESCE(SUM(token_count), 0) FROM chunks")
        image_count = await conn.fetchval("SELECT COUNT(*) FROM images")
        unique_images = await conn.fetchval("SELECT COUNT(DISTINCT phash) FROM images")
        chunk_image_count = await conn.fetchval("SELECT COUNT(*) FROM chunk_images")
        table_count = await conn.fetchval("SELECT COUNT(*) FROM tables")
        unique_tables = await conn.fetchval("SELECT COUNT(DISTINCT sha256) FROM tables")
        chunk_table_count = await conn.fetchval("SELECT COUNT(*) FROM chunk_tables")

        return {
            "documents": doc_count,
            "chunks": chunk_count,
            "embeddings": embedding_count,
            "pages": page_count,
            "layout_elements": element_count,
            "chunk_element_links": chunk_element_count,
            "total_tokens": total_tokens,
            "images": image_count,
            "unique_images": unique_images,
            "chunk_image_links": chunk_image_count,
            "tables": table_count,
            "unique_tables": unique_tables,
            "chunk_table_links": chunk_table_count,
            "embedding_model": AZURE_EMBEDDING_MODEL,
        }


# ── Chunks ────────────────────────────────────────────────────────────────


@app.get("/chunks/{chunk_id}", response_model=ChunkResponse)
async def get_chunk(chunk_id: int):
    """Get a single chunk with metadata."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT c.id AS chunk_id, c.content, c.document_id,
                   d.path AS document_path,
                   c.chunk_index, c.token_count, c.char_count,
                   c.headings, c.metadata
            FROM chunks c
            JOIN documents d ON d.id = c.document_id
            WHERE c.id = $1
            """,
            chunk_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail=f"Chunk with id {chunk_id} not found")

        metadata = row["metadata"]
        if isinstance(metadata, str):
            metadata = json.loads(metadata)

        return ChunkResponse(
            chunk_id=row["chunk_id"],
            content=row["content"],
            document_id=row["document_id"],
            document_path=row["document_path"],
            chunk_index=row["chunk_index"],
            token_count=row["token_count"],
            char_count=row["char_count"],
            headings=row["headings"],
            metadata=metadata or {},
        )


@app.get("/chunks/{chunk_id}/elements", response_model=List[LayoutElement])
async def get_chunk_elements(
    chunk_id: int,
    include_text: bool = Query(default=False),
):
    """Get layout elements linked to a chunk."""
    pool = await get_db_pool()
    text_col = ", le.full_text" if include_text else ""
    async with pool.acquire() as conn:
        chunk = await conn.fetchval("SELECT id FROM chunks WHERE id = $1", chunk_id)
        if not chunk:
            raise HTTPException(status_code=404, detail=f"Chunk {chunk_id} not found")

        rows = await conn.fetch(
            f"""
            SELECT le.id AS element_id, le.element_type, le.content_layer,
                   le.reading_order, le.page_number,
                   le.bbox_left, le.bbox_top, le.bbox_right, le.bbox_bottom,
                   le.text_preview{text_col}, le.heading_level,
                   le.group_label, le.children_count, le.metadata
            FROM chunk_elements ce
            JOIN layout_elements le ON le.id = ce.element_id
            WHERE ce.chunk_id = $1
            ORDER BY le.reading_order
            """,
            chunk_id,
        )
        def _parse_row(r):
            d = dict(r)
            if isinstance(d.get("metadata"), str):
                d["metadata"] = json.loads(d["metadata"])
            return LayoutElement(**d)
        return [_parse_row(r) for r in rows]


@app.get("/chunks/{chunk_id}/images", response_model=List[ImageResult])
async def get_chunk_images_endpoint(chunk_id: int):
    """Get images linked to a chunk."""
    images_by_chunk = await get_chunks_images_batch([chunk_id])
    return images_by_chunk.get(chunk_id, [])


@app.get("/chunks/{chunk_id}/tables", response_model=List[TableResult])
async def get_chunk_tables_endpoint(chunk_id: int):
    """Get tables linked to a chunk."""
    tables_by_chunk = await get_chunks_tables_batch([chunk_id])
    return tables_by_chunk.get(chunk_id, [])


# ── Pages & Elements ─────────────────────────────────────────────────────


@app.get("/pages/{page_id}/elements", response_model=List[LayoutElement])
async def get_page_elements(
    page_id: int,
    element_type: Optional[str] = None,
    include_text: bool = Query(default=False),
):
    """Get layout elements for a page, with optional type filter."""
    pool = await get_db_pool()
    text_col = ", full_text" if include_text else ""
    async with pool.acquire() as conn:
        page = await conn.fetchval("SELECT id FROM pages WHERE id = $1", page_id)
        if not page:
            raise HTTPException(status_code=404, detail=f"Page {page_id} not found")

        if element_type:
            rows = await conn.fetch(
                f"""
                SELECT id AS element_id, element_type, content_layer, reading_order,
                       page_number, bbox_left, bbox_top, bbox_right, bbox_bottom,
                       text_preview{text_col}, heading_level, group_label,
                       children_count, metadata
                FROM layout_elements
                WHERE page_id = $1 AND element_type = $2
                ORDER BY reading_order
                """,
                page_id, element_type,
            )
        else:
            rows = await conn.fetch(
                f"""
                SELECT id AS element_id, element_type, content_layer, reading_order,
                       page_number, bbox_left, bbox_top, bbox_right, bbox_bottom,
                       text_preview{text_col}, heading_level, group_label,
                       children_count, metadata
                FROM layout_elements
                WHERE page_id = $1
                ORDER BY reading_order
                """,
                page_id,
            )
        def _parse_row(r):
            d = dict(r)
            if isinstance(d.get("metadata"), str):
                d["metadata"] = json.loads(d["metadata"])
            return LayoutElement(**d)
        return [_parse_row(r) for r in rows]


@app.get("/elements/search", response_model=List[LayoutElement])
async def search_elements(
    document_id: int = Query(..., description="Document ID (required)"),
    element_type: Optional[str] = None,
    content_layer: Optional[str] = None,
    page_from: Optional[int] = None,
    page_to: Optional[int] = None,
    include_text: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=1000),
):
    """Search layout elements with filters."""
    pool = await get_db_pool()
    text_col = ", full_text" if include_text else ""

    conditions = ["document_id = $1"]
    params: list = [document_id]
    idx = 2

    if element_type:
        conditions.append(f"element_type = ${idx}")
        params.append(element_type)
        idx += 1
    if content_layer:
        conditions.append(f"content_layer = ${idx}")
        params.append(content_layer)
        idx += 1
    if page_from is not None:
        conditions.append(f"page_number >= ${idx}")
        params.append(page_from)
        idx += 1
    if page_to is not None:
        conditions.append(f"page_number <= ${idx}")
        params.append(page_to)
        idx += 1

    params.append(limit)
    where = " AND ".join(conditions)

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""
            SELECT id AS element_id, element_type, content_layer, reading_order,
                   page_number, bbox_left, bbox_top, bbox_right, bbox_bottom,
                   text_preview{text_col}, heading_level, group_label,
                   children_count, metadata
            FROM layout_elements
            WHERE {where}
            ORDER BY reading_order
            LIMIT ${idx}
            """,
            *params,
        )
        def _parse_row(r):
            d = dict(r)
            if isinstance(d.get("metadata"), str):
                d["metadata"] = json.loads(d["metadata"])
            return LayoutElement(**d)
        return [_parse_row(r) for r in rows]


# ── Tables ────────────────────────────────────────────────────────────────


@app.get("/tables")
async def list_tables(document_id: Optional[int] = None):
    """List all tables, optionally filtered by document."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        if document_id:
            rows = await conn.fetch(
                """
                SELECT t.id, t.document_id, d.path, t.page_number,
                       t.table_index, t.num_rows, t.num_cols,
                       t.caption, t.content_markdown, t.content_html, t.content_text
                FROM tables t JOIN documents d ON d.id = t.document_id
                WHERE t.document_id = $1
                ORDER BY t.page_number, t.table_index
                """,
                document_id,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT t.id, t.document_id, d.path, t.page_number,
                       t.table_index, t.num_rows, t.num_cols,
                       t.caption, t.content_markdown, t.content_html, t.content_text
                FROM tables t JOIN documents d ON d.id = t.document_id
                ORDER BY d.path, t.page_number, t.table_index
                """
            )
        return {"tables": [dict(r) for r in rows], "total": len(rows)}


@app.get("/tables/duplicates")
async def get_table_duplicates():
    """Find duplicate tables by sha256."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT t.sha256, COUNT(*) AS count,
                   array_agg(t.id) AS table_ids,
                   array_agg(DISTINCT d.path) AS document_paths
            FROM tables t
            JOIN documents d ON d.id = t.document_id
            GROUP BY t.sha256
            HAVING COUNT(*) > 1
            ORDER BY count DESC
            """
        )
        return {"duplicates": [dict(r) for r in rows], "total_groups": len(rows)}


@app.get("/tables/{table_id}")
async def get_table(table_id: int):
    """Get a single table by ID."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT t.id AS table_id, t.table_index, t.num_rows, t.num_cols,
                   t.page_number,
                   t.bbox_left, t.bbox_top, t.bbox_right, t.bbox_bottom,
                   t.caption, t.label,
                   t.content_markdown, t.content_html, t.content_text,
                   t.sha256, t.extracted_at, t.metadata,
                   d.path AS document_path, d.id AS document_id
            FROM tables t
            JOIN documents d ON d.id = t.document_id
            WHERE t.id = $1
            """,
            table_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail=f"Table with id {table_id} not found")
        return dict(row)


# ── Images ────────────────────────────────────────────────────────────────


@app.get("/images")
async def list_images(document_id: Optional[int] = None):
    """List all images, optionally filtered by document."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        if document_id:
            rows = await conn.fetch(
                """
                SELECT i.id, i.document_id, d.path, i.page_number,
                       i.file_path, i.caption, i.label, i.width, i.height, i.image_index
                FROM images i JOIN documents d ON d.id = i.document_id
                WHERE i.document_id = $1
                ORDER BY i.page_number, i.image_index
                """,
                document_id,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT i.id, i.document_id, d.path, i.page_number,
                       i.file_path, i.caption, i.label, i.width, i.height, i.image_index
                FROM images i JOIN documents d ON d.id = i.document_id
                ORDER BY d.path, i.page_number, i.image_index
                """
            )
        return {"images": [dict(r) for r in rows], "total": len(rows)}


@app.get("/images/duplicates")
async def get_image_duplicates():
    """Find duplicate images by perceptual hash."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT i.phash, COUNT(*) AS count,
                   array_agg(i.id) AS image_ids,
                   array_agg(DISTINCT d.path) AS document_paths
            FROM images i
            JOIN documents d ON d.id = i.document_id
            GROUP BY i.phash
            HAVING COUNT(*) > 1
            ORDER BY count DESC
            """
        )
        return {"duplicates": [dict(r) for r in rows], "total_groups": len(rows)}


@app.get("/images/{image_id}")
async def get_image(image_id: int):
    """Get a single image's metadata."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT i.id AS image_id, i.file_path, i.file_size, i.mime_type,
                   i.width, i.height, i.page_number,
                   i.bbox_left, i.bbox_top, i.bbox_right, i.bbox_bottom,
                   i.caption, i.label, i.image_index,
                   i.phash, i.sha256, i.extracted_at, i.metadata,
                   d.path AS document_path, d.id AS document_id
            FROM images i
            JOIN documents d ON d.id = i.document_id
            WHERE i.id = $1
            """,
            image_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail=f"Image with id {image_id} not found")
        return dict(row)


@app.get("/images/{image_id}/file")
async def get_image_file(image_id: int):
    """Serve an image file by its database ID."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT file_path, mime_type FROM images WHERE id = $1", image_id
        )
    if not row:
        raise HTTPException(status_code=404, detail=f"Image with id {image_id} not found")

    file_path = IMAGES_PATH / row["file_path"]
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="Image file not found on disk")

    return FileResponse(
        path=str(file_path),
        media_type=row.get("mime_type") or "image/png",
        filename=file_path.name,
    )


# ── Config ────────────────────────────────────────────────────────────────


@app.get("/config")
async def get_config():
    """Return pipeline configuration settings."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT key, value, label, description, updated_at "
            "FROM pipeline_config ORDER BY key"
        )
        return [dict(r) for r in rows]


@app.put("/config")
async def update_config(updates: dict):
    """Update pipeline configuration settings."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        for key, value in updates.items():
            await conn.execute(
                "UPDATE pipeline_config SET value = $1, updated_at = NOW() WHERE key = $2",
                str(value), key
            )
    return {"status": "ok"}


# ── Multi-Index Endpoints ────────────────────────────────────────────────


@app.get("/indexes")
async def list_indexes():
    """List all indexes with document counts."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT i.id, i.slug, i.display_name, i.description, i.created_at,
                   COUNT(d.id) AS document_count
            FROM indexes i
            LEFT JOIN documents d ON d.index_id = i.id
            GROUP BY i.id
            ORDER BY i.created_at
        """)
        return [dict(r) for r in rows]


@app.post("/indexes")
async def create_index(body: IndexCreate):
    """Create a new index (DB row + ingestion subfolder)."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        existing = await conn.fetchrow(
            "SELECT id FROM indexes WHERE slug = $1", body.slug
        )
        if existing:
            raise HTTPException(status_code=409, detail=f"Index '{body.slug}' already exists")

        row = await conn.fetchrow(
            "INSERT INTO indexes (slug, display_name, description) "
            "VALUES ($1, $2, $3) RETURNING id, slug, display_name, description, created_at",
            body.slug, body.display_name, body.description,
        )

    subfolder = INGEST_PATH / body.slug
    subfolder.mkdir(parents=True, exist_ok=True)
    return dict(row)


@app.delete("/indexes/{slug}")
async def delete_index(slug: str):
    """Delete an empty index."""
    if slug == "default":
        raise HTTPException(status_code=400, detail="Cannot delete the default index")

    pool = await get_db_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT i.id, COUNT(d.id) AS doc_count "
            "FROM indexes i LEFT JOIN documents d ON d.index_id = i.id "
            "WHERE i.slug = $1 GROUP BY i.id",
            slug,
        )
        if not row:
            raise HTTPException(status_code=404, detail=f"Index '{slug}' not found")
        if row["doc_count"] > 0:
            raise HTTPException(
                status_code=409,
                detail=f"Index '{slug}' has {row['doc_count']} document(s). Remove them first.",
            )
        await conn.execute("DELETE FROM indexes WHERE id = $1", row["id"])

    subfolder = INGEST_PATH / slug
    if subfolder.is_dir():
        try:
            subfolder.rmdir()
        except OSError:
            pass
    return {"status": "ok", "message": f"Index '{slug}' deleted"}


# ── Wiki ──────────────────────────────────────────────────────────────────

# Strong references to background wiki-build tasks — prevents GC cancellation.
_wiki_tasks: set = set()


def _build_llm():
    return wiki.MiniMaxLLM(_chat_client, _CHAT_MODEL)


def _build_embedder():
    return wiki.AzureEmbedder(get_openai_client(), AZURE_EMBEDDING_MODEL)


@app.post("/indexes/{slug}/wiki/build")
async def build_wiki(slug: str):
    """Enqueue an autonomous wiki build for an index. Rejects if one is already running."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        index_id = await conn.fetchval("SELECT id FROM indexes WHERE slug = $1", slug)
        if index_id is None:
            raise HTTPException(status_code=404, detail=f"Index '{slug}' not found")
        active = await conn.fetchval(
            "SELECT id FROM wiki_jobs WHERE index_id = $1 "
            "AND status NOT IN ('completed', 'failed') LIMIT 1", index_id)
        if active is not None:
            raise HTTPException(status_code=409, detail="A wiki build is already in progress for this index")
        try:
            job_id = await conn.fetchval(
                "INSERT INTO wiki_jobs (index_id, status) VALUES ($1, 'queued') RETURNING id",
                index_id)
        except asyncpg.UniqueViolationError:
            raise HTTPException(status_code=409, detail="A wiki build is already in progress for this index")

    from datetime import datetime, timezone
    ts = datetime.now(timezone.utc).isoformat()
    task = asyncio.create_task(
        wiki.run_wiki_build(pool, _build_llm(), _build_embedder(), slug, job_id, ts))
    if hasattr(task, "add_done_callback"):
        _wiki_tasks.add(task)
        task.add_done_callback(_wiki_tasks.discard)
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
                # Close the stream once the build reaches a terminal state (or no job
                # exists). Nothing further will change, so polling forever just holds
                # the connection open — clients reconnect/refetch if needed.
                if payload.get("status") in ("completed", "failed", "none"):
                    return
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


# ── Upload ────────────────────────────────────────────────────────────────


@app.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    index_slug: str = Form("default"),
):
    """Upload a document to a specific index."""
    suffix = Path(file.filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported file type '{suffix}'. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    pool = await get_db_pool()
    async with pool.acquire() as conn:
        index_row = await conn.fetchrow(
            "SELECT id FROM indexes WHERE slug = $1", index_slug
        )
    if not index_row:
        raise HTTPException(status_code=404, detail=f"Index '{index_slug}' not found")

    file_content = await file.read()
    sha256 = hashlib.sha256(file_content).hexdigest()

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id FROM documents WHERE sha256 = $1 AND index_id = $2",
            sha256, index_row["id"],
        )
    if row:
        return {"status": "known", "message": "File already ingested in this index"}

    dest_dir = INGEST_PATH / index_slug
    dest_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(file.filename).stem
    dest = dest_dir / file.filename
    if dest.exists():
        dest = dest_dir / f"{stem}_{int(time.time())}{suffix}"
    dest.write_bytes(file_content)
    # Touch parent ingest dir so systemd PathModified watcher triggers
    INGEST_PATH.touch()

    # Create ingestion job row for pipeline tracking
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO ingestion_jobs (filename, index_slug, status) VALUES ($1, $2, 'queued')",
            dest.name, index_slug,
        )

    return {
        "status": "queued",
        "filename": dest.name,
        "index_slug": index_slug,
        "message": f"File queued for ingestion into '{index_slug}'",
    }



# ── Ingestion Pipeline Status ─────────────────────────────────────────


@app.get("/ingestion/status")
async def get_ingestion_status(index_slug: str = None):
    """Return active jobs plus recently completed (within 60 seconds)."""
    pool = await get_db_pool()
    query = """
        SELECT id, filename, index_slug, status, progress,
               document_id, error_message, created_at, started_at,
               updated_at, completed_at
        FROM ingestion_jobs
        WHERE (status NOT IN ('completed', 'failed')
               OR completed_at > NOW() - INTERVAL '60 seconds')
    """
    params = []
    if index_slug:
        query += " AND index_slug = $1"
        params.append(index_slug)
    query += " ORDER BY created_at DESC"

    async with pool.acquire() as conn:
        rows = await conn.fetch(query, *params)
        return [
            {
                "id": r["id"],
                "filename": r["filename"],
                "index_slug": r["index_slug"],
                "status": r["status"],
                "progress": json.loads(r["progress"]) if isinstance(r["progress"], str) else r["progress"],
                "document_id": r["document_id"],
                "error_message": r["error_message"],
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                "started_at": r["started_at"].isoformat() if r["started_at"] else None,
                "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None,
                "completed_at": r["completed_at"].isoformat() if r["completed_at"] else None,
            }
            for r in rows
        ]


@app.get("/ingestion/stream")
async def ingestion_stream(index_slug: str = None):
    """SSE endpoint for real-time ingestion status updates."""

    async def event_generator():
        last_state = None
        pool = await get_db_pool()
        while True:
            query = """
                SELECT id, filename, index_slug, status, progress,
                       document_id, error_message, created_at, started_at,
                       updated_at, completed_at
                FROM ingestion_jobs
                WHERE (status NOT IN ('completed', 'failed')
                       OR completed_at > NOW() - INTERVAL '60 seconds')
            """
            params = []
            if index_slug:
                query += " AND index_slug = $1"
                params.append(index_slug)
            query += " ORDER BY created_at DESC"

            try:
                async with pool.acquire() as conn:
                    rows = await conn.fetch(query, *params)
                    jobs = [
                        {
                            "id": r["id"],
                            "filename": r["filename"],
                            "index_slug": r["index_slug"],
                            "status": r["status"],
                            "progress": json.loads(r["progress"]) if isinstance(r["progress"], str) else r["progress"],
                            "document_id": r["document_id"],
                            "error_message": r["error_message"],
                            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                            "started_at": r["started_at"].isoformat() if r["started_at"] else None,
                            "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None,
                            "completed_at": r["completed_at"].isoformat() if r["completed_at"] else None,
                        }
                        for r in rows
                    ]

                current_state = json.dumps(jobs, sort_keys=True)
                if current_state != last_state:
                    yield f"data: {json.dumps(jobs)}\n\n"
                    last_state = current_state
                else:
                    yield ": keepalive\n\n"

            except Exception as e:
                logger.warning("sse_poll_error", error=str(e))
                yield f"data: {json.dumps({'error': str(e)})}\n\n"

            await asyncio.sleep(2)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

# ── Chat Agent ───────────────────────────────────────────────────
from openai import AsyncOpenAI as _AsyncOpenAI

_chat_client = _AsyncOpenAI(
    api_key=os.environ.get("MINIMAX_API_KEY", ""),
    base_url="https://api.minimaxi.chat/v1",
)
_CHAT_MODEL = os.environ.get("CHAT_MODEL", "MiniMax-M2.7")

_CHAT_SYSTEM_PROMPT = """You are Felix, a document intelligence assistant. You help users understand and explore their ingested documents.

Guidelines:
- Use search_documents ONLY when the user asks about document content, specific topics, or information that would be in their documents.
- Do NOT search for greetings, capability questions, or general conversation — just respond directly.
- When you do search, synthesize an answer grounded in the results and cite sources by document name.
- If a search returns no relevant results, say so honestly.
- Keep answers concise but thorough. Use markdown formatting."""

_SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "search_documents",
        "description": "Search ingested documents for relevant information. Use this to find facts, data, or context to answer the user's question.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "top_k": {"type": "integer", "description": "Number of results (default 5)", "default": 5},
            },
            "required": ["query"],
        },
    },
}


class ChatRequest(BaseModel):
    message: str
    history: list[dict] = []
    index_slug: Optional[str] = None
    show_thinking: bool = False


async def _execute_document_search(query: str, top_k: int = 5) -> list[dict]:
    """Execute hybrid search using existing infrastructure."""
    embedding = await generate_embedding(query)
    vector_task = search_similar_chunks(embedding, top_k=top_k, threshold=0.0)
    keyword_task = search_fulltext_chunks(query, top_k=top_k)
    vector_results, keyword_results = await asyncio.gather(vector_task, keyword_task)
    return reciprocal_rank_fusion(vector_results, keyword_results, top_k=top_k)


@app.post("/chat")
async def chat(request: ChatRequest):
    async def event_generator():
        messages = [{"role": "system", "content": _CHAT_SYSTEM_PROMPT}]
        for msg in request.history:
            messages.append({"role": msg["role"], "content": msg["content"]})
        messages.append({"role": "user", "content": request.message})

        citations = []
        max_tool_rounds = 3

        for _ in range(max_tool_rounds + 1):
            stream = await _chat_client.chat.completions.create(
                model=_CHAT_MODEL,
                messages=messages,
                tools=[_SEARCH_TOOL],
                stream=True,
            )

            collected_content = ""
            tool_calls_acc = {}
            _in_think = False
            _think_buf = ""

            async for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                finish_reason = chunk.choices[0].finish_reason

                if delta.content:
                    collected_content += delta.content
                    # Strip <think>...</think> blocks unless show_thinking is on
                    text = delta.content
                    if request.show_thinking:
                        event = {"type": "token", "content": text}
                        yield f"data: {json.dumps(event)}\n\n"
                        continue
                    if _in_think:
                        _think_buf += text
                        if "</think>" in _think_buf:
                            after = _think_buf.split("</think>", 1)[1]
                            _in_think = False
                            _think_buf = ""
                            if after and after.strip():
                                event = {"type": "token", "content": after}
                                yield f"data: {json.dumps(event)}\n\n"
                        continue
                    if "<think>" in text:
                        before, rest = text.split("<think>", 1)
                        if before:
                            event = {"type": "token", "content": before}
                            yield f"data: {json.dumps(event)}\n\n"
                        if "</think>" in rest:
                            after = rest.split("</think>", 1)[1]
                            if after and after.strip():
                                event = {"type": "token", "content": after}
                                yield f"data: {json.dumps(event)}\n\n"
                        else:
                            _in_think = True
                            _think_buf = rest
                        continue
                    event = {"type": "token", "content": text}
                    yield f"data: {json.dumps(event)}\n\n"

                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = tc.index
                        if idx not in tool_calls_acc:
                            tool_calls_acc[idx] = {"id": tc.id or "", "name": "", "arguments": ""}
                        if tc.id:
                            tool_calls_acc[idx]["id"] = tc.id
                        if tc.function:
                            if tc.function.name:
                                tool_calls_acc[idx]["name"] = tc.function.name
                            if tc.function.arguments:
                                tool_calls_acc[idx]["arguments"] += tc.function.arguments

            if not tool_calls_acc:
                break

            assistant_msg = {"role": "assistant", "content": collected_content or None}
            assistant_msg["tool_calls"] = [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {"name": tc["name"], "arguments": tc["arguments"]},
                }
                for tc in tool_calls_acc.values()
            ]
            messages.append(assistant_msg)

            for tc in tool_calls_acc.values():
                if tc["name"] == "search_documents":
                    try:
                        args = json.loads(tc["arguments"])
                    except json.JSONDecodeError:
                        args = {"query": request.message}

                    query = args.get("query", request.message)
                    top_k = args.get("top_k", 5)

                    tc_event = {"type": "tool_call", "name": "search_documents", "query": query}
                    yield f"data: {json.dumps(tc_event)}\n\n"

                    results = await _execute_document_search(query, top_k=top_k)

                    for r in results:
                        citations.append({
                            "chunk_id": r["chunk_id"],
                            "document_path": r.get("document_path", ""),
                            "content": r["content"][:200] if r.get("content") else "",
                            "similarity": float(r.get("similarity", 0)),
                        })

                    tool_response = "\n\n".join(
                        "[Document: {}]\n{}".format(r.get("document_path", "unknown"), r["content"])
                        for r in results
                    ) if results else "No relevant documents found."

                    tr_event = {"type": "tool_result", "results": len(results)}
                    yield f"data: {json.dumps(tr_event)}\n\n"

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": tool_response,
                    })

        # Deduplicate by chunk_id, keep highest similarity, filter low-relevance
        seen = {}
        for c in citations:
            cid = c["chunk_id"]
            if cid not in seen or c["similarity"] > seen[cid]["similarity"]:
                seen[cid] = c
        unique_citations = sorted(seen.values(), key=lambda x: x["similarity"], reverse=True)
        unique_citations = [c for c in unique_citations if c["similarity"] > 0.02][:3]

        done_event = {"type": "done", "citations": unique_citations}
        yield f"data: {json.dumps(done_event)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)

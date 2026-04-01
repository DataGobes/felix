# Felix — Key Decisions

## Docling for document conversion

Open-source document understanding library from IBM. Handles PDF, DOCX, PPTX, XLSX, HTML, and Markdown. Extracts rich layout information including bounding boxes, reading order, tables (via TableFormer), and images. No per-document API cost. The alternative was Azure Document Intelligence, but Docling provides deeper structural metadata and runs locally.

## pgvector for embeddings

Stores vector embeddings directly in PostgreSQL using the pgvector extension. This avoids running a separate vector database (Pinecone, Qdrant, etc.) and keeps all data — documents, chunks, embeddings, layout elements — in a single database with full SQL joins and transactions.

## Azure OpenAI text-embedding-3-small (1536d)

Uses the 1536-dimensional embedding model available on an existing Azure OpenAI subscription. Good balance of quality and cost. The embedding dimension matches the pgvector column definition in init.sql.

## FastAPI backend

Two separate services: ingestion worker (long-running document processing) and search API (low-latency queries). FastAPI provides async support, streaming SSE for real-time ingestion status updates, and automatic OpenAPI documentation.

## React/Vite frontend with shadcn/ui

React 19 with Vite for fast development iteration. shadcn/ui provides accessible, composable UI primitives built on Radix UI. Tailwind CSS for styling. The frontend is served via Nginx which also proxies API requests to the backend.

## CPU-only ingestion by default, optional GPU offload

The default Docker setup uses CPU-only PyTorch for document conversion (~1.7GB image vs ~9.7GB with CUDA). An optional GPU service can be started with `docker compose --profile gpu up` for faster conversion on machines with NVIDIA GPUs.

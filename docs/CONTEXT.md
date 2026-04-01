# Felix

## What is this
Document intelligence platform. Upload any business document, Felix
decomposes it into structured elements (pages, headings, tables, images,
layout bounding boxes), generates semantic embeddings, and provides
search + AI chat over the corpus. Built on Docling + pgvector + FastAPI + React.

## Current status
- Phase: building (standalone extraction from alfred-planning)
- Last updated: 2026-04-01
- Active branch: main

## Key decisions (summary)
- Docling for conversion — open-source, no API cost, rich layout extraction
- pgvector for embeddings — stays with PostgreSQL, no separate vector DB
- Azure OpenAI text-embedding-3-small (1536d) — available on existing subscription
- FastAPI backend — async, streaming SSE for ingestion status
- React/Vite frontend — fast dev, shadcn/ui components
→ Full decisions in DECISIONS.md

## Next actions
- [ ] Retheme dashboard: Matrix → business professional
- [ ] Deploy to Azure Container Apps
- [ ] Add sample documents for demo
- [ ] Wire up felix.datagobes.dev subdomain

# Felix

Document intelligence platform. Upload any business document — PDF, DOCX, PPTX, XLSX, TXT, or Markdown — and Felix decomposes it into structured elements (pages, headings, tables, images, layout bounding boxes), generates semantic embeddings, and provides search and AI chat over the corpus.

## Architecture

```
                    ┌──────────────────────────────────┐
                    │           felix-frontend          │
                    │         (React / Nginx)           │
                    │            :5180                  │
                    └───────────────┬──────────────────┘
                                    │ /api/*
                                    ▼
                    ┌──────────────────────────────────┐
                    │            felix-api              │
                    │      (FastAPI search + chat)      │
                    │            :8001                  │
                    └───────────────┬──────────────────┘
                                    │
                    ┌───────────────┴──────────────────┐
                    │                                   │
                    ▼                                   ▼
    ┌──────────────────────┐          ┌──────────────────────────┐
    │   felix-postgres     │          │    felix-ingestion       │
    │   (pgvector/pg16)    │◄─────────│    (Docling worker)      │
    │   documents, chunks, │          │    convert, chunk,       │
    │   embeddings, layout │          │    embed, extract        │
    └──────────────────────┘          └──────────────────────────┘
```

## Features

- **Document ingestion** — automatic conversion via Docling with progress streaming
- **Semantic search** — vector similarity search over document chunks using pgvector
- **AI chat** — conversational Q&A over your document corpus with source citations
- **Structure navigation** — browse document hierarchy, headings, reading order
- **Table & image extraction** — structured table data with cell-level detail, images with dedup
- **Layout analysis** — bounding boxes, element types, page-level spatial metadata

## Supported Formats

PDF, DOCX, PPTX, XLSX, TXT, Markdown

## Quick Start

```bash
# Clone
git clone https://github.com/datagobes/felix.git
cd felix

# Configure
cp .env.example .env
# Edit .env with your Azure OpenAI credentials and a Postgres password

# Run
docker compose up -d
```

- Frontend: http://localhost:5180
- API: http://localhost:8001/health

### GPU Mode (optional)

If you have an NVIDIA GPU, start with GPU-accelerated document conversion:

```bash
docker compose --profile gpu up -d
```

Set `ENABLE_GPU_CONVERSION=true` in your `.env`.

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Document conversion | [Docling](https://github.com/DS4SD/docling) |
| Vector database | PostgreSQL 16 + [pgvector](https://github.com/pgvector/pgvector) |
| Embeddings | Azure OpenAI text-embedding-3-small (1536d) |
| Search API | Python 3.11 / FastAPI |
| Frontend | React 19 / Vite / Tailwind CSS / shadcn/ui |
| Reverse proxy | Nginx |
| Orchestration | Docker Compose |

## Screenshots

*Coming soon*

## License

[MIT](LICENSE)

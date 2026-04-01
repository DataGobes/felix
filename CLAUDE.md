# CLAUDE.md

## What is Felix

Document intelligence platform — upload documents, extract structure, search semantically, chat with AI. Built on Docling + pgvector + FastAPI + React.

## Repository Structure

```
felix/
├── backend/          # Python — ingestion worker + FastAPI search API
├── frontend/         # React 19 / Vite / Tailwind / shadcn/ui
├── docker-compose.yml
└── docs/             # CONTEXT.md, DECISIONS.md, RESEARCH.md
```

## Running

```bash
cp .env.example .env   # fill in credentials
docker compose up -d   # starts postgres, api, ingestion, frontend
```

- Frontend: http://localhost:5180
- API: http://localhost:8001/health
- GPU mode: `docker compose --profile gpu up -d`

## Backend

Two services from the same `backend/` directory:

- **felix-api** (`search.py` via `Dockerfile.search`) — FastAPI search/chat API on port 8001
- **felix-ingestion** (`ingestion.py` via `Dockerfile`) — Docling conversion worker

### Testing

```bash
cd backend
pip install -r requirements.test.txt
pytest -v
```

## Frontend

React 19 SPA served via Nginx. Nginx proxies `/api/*` to felix-api.

```bash
cd frontend
npm install
npm run dev       # Vite dev server
npm run build     # production build
npm run lint      # ESLint
```

API base URL is configured via `VITE_API_URL` env var (defaults to `/api`).

## Key Files

| File | Purpose |
|------|---------|
| `backend/ingestion.py` | Document processing pipeline — Docling conversion, chunking, embedding, layout extraction |
| `backend/search.py` | FastAPI API — semantic search, document management, chat, ingestion status |
| `backend/init.sql` | Full database schema (pgvector, 13 tables, views, functions) |
| `frontend/src/api/client.jsx` | API client — all backend calls |
| `frontend/nginx.conf` | Nginx reverse proxy config |

## Database

PostgreSQL 16 with pgvector. Schema is in `backend/init.sql`. Key tables: documents, chunks, embeddings, images, tables, table_cells, pages, layout_elements, indexes, ingestion_jobs.

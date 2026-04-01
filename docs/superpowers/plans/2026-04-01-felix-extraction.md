# Felix Repository Extraction — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract the Felix document intelligence platform from alfred-planning/mission-control into a standalone repository with clean docker compose, unified branding, and professional documentation.

**Architecture:** Direct file copy from `~/Projects/alfred-planning/mission-control/` into `~/Projects/felix/`, with targeted transforms: API URL consolidation, nginx upstream renames, metrics removal, docker compose rewrite, branding update, and init.sql merge.

**Tech Stack:** Python 3.11 (FastAPI, Docling), React 19 (Vite, Tailwind, shadcn/ui), PostgreSQL 16 (pgvector), Docker Compose, Nginx

---

## File Structure

```
felix/
├── backend/
│   ├── ingestion.py              # copy as-is
│   ├── search.py                 # copy as-is
│   ├── gpu_convert_service.py    # copy as-is
│   ├── init.sql                  # copy + append ingestion_jobs table
│   ├── Dockerfile                # copy as-is
│   ├── Dockerfile.search         # copy as-is
│   ├── Dockerfile.gpu            # copy as-is
│   ├── requirements.txt          # copy as-is
│   ├── requirements.search.txt   # copy as-is
│   ├── requirements.gpu.txt      # copy as-is
│   ├── requirements.test.txt     # copy as-is
│   ├── conftest.py               # copy as-is
│   ├── test_ingestion.py         # copy as-is
│   ├── test_search.py            # copy as-is
│   └── pytest.ini                # copy as-is
├── frontend/
│   ├── src/                      # copy entire tree, modify api/client.jsx
│   ├── public/
│   │   └── felix-logo.svg        # new: brand mark SVG
│   ├── index.html                # copy, update favicon path
│   ├── package.json              # copy as-is
│   ├── vite.config.js            # copy as-is
│   ├── tailwind.config.js        # copy as-is
│   ├── postcss.config.js         # copy as-is
│   ├── jsconfig.json             # copy as-is
│   ├── eslint.config.js          # copy as-is
│   ├── components.json           # copy as-is
│   ├── Dockerfile                # copy as-is
│   └── nginx.conf                # copy, update upstreams + remove metrics
├── docker-compose.yml            # new: standalone felix network
├── .env.example                  # new: documented env vars
├── .gitignore                    # new
├── LICENSE                       # new: MIT
├── CLAUDE.md                     # new: project instructions
├── README.md                     # new: professional README
└── docs/
    ├── CONTEXT.md                # new: project context
    ├── RESEARCH.md               # new: placeholder
    └── DECISIONS.md              # new: key decisions with rationale
```

---

### Task 1: Copy backend files

**Files:**
- Create: `backend/` directory with 15 files copied from `~/Projects/alfred-planning/mission-control/rag/`

- [ ] **Step 1: Copy Python source files**

```bash
SRC=~/Projects/alfred-planning/mission-control/rag
DST=~/Projects/felix/backend
mkdir -p "$DST"
cp "$SRC/ingestion.py" "$DST/"
cp "$SRC/search.py" "$DST/"
cp "$SRC/gpu_convert_service.py" "$DST/"
```

- [ ] **Step 2: Copy Dockerfiles**

```bash
SRC=~/Projects/alfred-planning/mission-control/rag
DST=~/Projects/felix/backend
cp "$SRC/Dockerfile" "$DST/"
cp "$SRC/Dockerfile.search" "$DST/"
cp "$SRC/Dockerfile.gpu" "$DST/"
```

- [ ] **Step 3: Copy requirements files**

```bash
SRC=~/Projects/alfred-planning/mission-control/rag
DST=~/Projects/felix/backend
cp "$SRC/requirements.txt" "$DST/"
cp "$SRC/requirements.search.txt" "$DST/"
cp "$SRC/requirements.gpu.txt" "$DST/"
cp "$SRC/requirements.test.txt" "$DST/"
```

- [ ] **Step 4: Copy test files**

```bash
SRC=~/Projects/alfred-planning/mission-control/rag
DST=~/Projects/felix/backend
cp "$SRC/conftest.py" "$DST/"
cp "$SRC/test_ingestion.py" "$DST/"
cp "$SRC/test_search.py" "$DST/"
cp "$SRC/pytest.ini" "$DST/"
```

- [ ] **Step 5: Copy init.sql and append ingestion_jobs table**

```bash
SRC=~/Projects/alfred-planning/mission-control/rag
DST=~/Projects/felix/backend
cp "$SRC/init.sql" "$DST/"
```

Then append to `backend/init.sql` (after the last line):

```sql

-- ─── Ingestion Jobs (pipeline status tracking) ─────────────────

CREATE TABLE IF NOT EXISTS ingestion_jobs (
  id            SERIAL PRIMARY KEY,
  filename      VARCHAR(500) NOT NULL,
  index_slug    VARCHAR(100) NOT NULL DEFAULT 'default',
  status        VARCHAR(50)  NOT NULL DEFAULT 'queued',
  progress      JSONB        NOT NULL DEFAULT '{}',
  document_id   INTEGER,
  error_message TEXT,
  created_at    TIMESTAMP    NOT NULL DEFAULT NOW(),
  started_at    TIMESTAMP,
  updated_at    TIMESTAMP    NOT NULL DEFAULT NOW(),
  completed_at  TIMESTAMP
);

-- Partial index: only index active jobs for fast polling queries
CREATE INDEX IF NOT EXISTS idx_ingestion_jobs_active
  ON ingestion_jobs (status) WHERE status NOT IN ('completed', 'failed');

-- Index for cleanup queries on completed_at
CREATE INDEX IF NOT EXISTS idx_ingestion_jobs_completed_at
  ON ingestion_jobs (completed_at) WHERE completed_at IS NOT NULL;

COMMENT ON TABLE ingestion_jobs IS 'Pipeline status tracking for document ingestion jobs';
```

- [ ] **Step 6: Verify all backend files exist**

```bash
ls -la ~/Projects/felix/backend/
```

Expected: 15 files (3 .py source, 3 Dockerfiles, 4 requirements, 1 .sql, 4 test files)

- [ ] **Step 7: Commit**

```bash
cd ~/Projects/felix
git add backend/
git commit -m "feat: extract backend from alfred-planning/mission-control/rag"
```

---

### Task 2: Copy frontend files

**Files:**
- Create: `frontend/` directory with source tree, config files, Dockerfile, nginx.conf

- [ ] **Step 1: Copy src directory**

```bash
SRC=~/Projects/alfred-planning/mission-control/dashboard
DST=~/Projects/felix/frontend
mkdir -p "$DST"
cp -r "$SRC/src" "$DST/"
```

- [ ] **Step 2: Copy config files and lock file**

```bash
SRC=~/Projects/alfred-planning/mission-control/dashboard
DST=~/Projects/felix/frontend
cp "$SRC/package.json" "$DST/"
cp "$SRC/package-lock.json" "$DST/"
cp "$SRC/vite.config.js" "$DST/"
cp "$SRC/tailwind.config.js" "$DST/"
cp "$SRC/postcss.config.js" "$DST/"
cp "$SRC/jsconfig.json" "$DST/"
cp "$SRC/eslint.config.js" "$DST/"
cp "$SRC/components.json" "$DST/"
```

- [ ] **Step 3: Copy Dockerfile and nginx.conf**

```bash
SRC=~/Projects/alfred-planning/mission-control/dashboard
DST=~/Projects/felix/frontend
cp "$SRC/Dockerfile" "$DST/"
cp "$SRC/nginx.conf" "$DST/"
```

- [ ] **Step 4: Copy index.html**

```bash
SRC=~/Projects/alfred-planning/mission-control/dashboard
DST=~/Projects/felix/frontend
cp "$SRC/index.html" "$DST/"
```

- [ ] **Step 5: Create public directory (skip vite.svg)**

```bash
mkdir -p ~/Projects/felix/frontend/public
```

- [ ] **Step 6: Verify all frontend files exist**

```bash
ls -la ~/Projects/felix/frontend/
ls ~/Projects/felix/frontend/src/
ls ~/Projects/felix/frontend/src/components/
ls ~/Projects/felix/frontend/src/pages/
```

Expected: `src/` tree with api/, components/ (9 + ui/), pages/ (DocumentViewer + viewers/), hooks/, lib/. Plus 7 config files, Dockerfile, nginx.conf, index.html.

- [ ] **Step 7: Commit**

```bash
cd ~/Projects/felix
git add frontend/
git commit -m "feat: extract frontend from alfred-planning/mission-control/dashboard"
```

---

### Task 3: Transform frontend — API client, nginx, index.html

**Files:**
- Modify: `frontend/src/api/client.jsx`
- Modify: `frontend/nginx.conf`
- Modify: `frontend/index.html`

- [ ] **Step 1: Rewrite API client to use single VITE_API_URL**

Replace the first two lines of `frontend/src/api/client.jsx`:

```javascript
const METRICS_URL = import.meta.env.VITE_METRICS_URL || '/api'
const RAG_URL = import.meta.env.VITE_RAG_URL || '/api'
```

With:

```javascript
const API_URL = import.meta.env.VITE_API_URL || '/api'
```

Then replace all occurrences of `METRICS_URL` and `RAG_URL` with `API_URL` throughout the file. Every fetch call uses the same base URL now.

- [ ] **Step 2: Update nginx.conf — rename upstreams, remove metrics**

Replace the full contents of `frontend/nginx.conf` with:

```nginx
server {
    listen 5180;
    server_name _;

    client_max_body_size 50m;

    root /usr/share/nginx/html;
    index index.html;

    resolver 127.0.0.11 valid=30s;

    # SSE endpoint: disable buffering for real-time streaming
    location /api/ingestion/stream {
        proxy_pass http://felix-api:8001/ingestion/stream;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_buffering off;
        proxy_cache off;
        proxy_set_header Connection '';
        proxy_http_version 1.1;
        chunked_transfer_encoding off;
        proxy_read_timeout 86400s;
    }

    # SSE endpoint: chat streaming (tool-calling agent loop)
    location /api/chat {
        proxy_pass http://felix-api:8001/chat;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_buffering off;
        proxy_cache off;
        proxy_set_header Connection '';
        proxy_http_version 1.1;
        chunked_transfer_encoding off;
        proxy_read_timeout 300s;
    }

    # Prefix match: all other /api/ calls → felix-api service
    location /api/ {
        proxy_pass http://felix-api:8001/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # Hashed assets: cache aggressively
    location /assets/ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    # SPA fallback: no-cache on index.html so new deploys are picked up
    location / {
        add_header Cache-Control "no-cache";
        try_files $uri $uri/ /index.html;
    }
}
```

- [ ] **Step 3: Update index.html favicon**

In `frontend/index.html`, replace:

```html
<link rel="icon" type="image/svg+xml" href="/vite.svg" />
```

With:

```html
<link rel="icon" type="image/svg+xml" href="/felix-logo.svg" />
```

Also remove the Share Tech Mono Google Fonts link (that's the Matrix theme font):

```html
<link href="https://fonts.googleapis.com/css2?family=Share+Tech+Mono&display=swap" rel="stylesheet">
```

- [ ] **Step 4: Verify changes**

```bash
head -3 ~/Projects/felix/frontend/src/api/client.jsx
grep -c "API_URL" ~/Projects/felix/frontend/src/api/client.jsx
grep -c "RAG_URL\|METRICS_URL" ~/Projects/felix/frontend/src/api/client.jsx
grep "felix-api" ~/Projects/felix/frontend/nginx.conf
grep "metrics" ~/Projects/felix/frontend/nginx.conf
grep "felix-logo" ~/Projects/felix/frontend/index.html
```

Expected: API_URL used throughout, no RAG_URL/METRICS_URL remaining, felix-api in nginx, no metrics in nginx, felix-logo in index.html.

- [ ] **Step 5: Commit**

```bash
cd ~/Projects/felix
git add frontend/
git commit -m "refactor: consolidate API URL, update nginx upstreams, remove metrics"
```

---

### Task 4: Create felix-logo.svg and update App.jsx header

**Files:**
- Create: `frontend/public/felix-logo.svg`
- Modify: `frontend/src/App.jsx`

- [ ] **Step 1: Create felix-logo.svg**

Write `frontend/public/felix-logo.svg`:

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 40 40" width="40" height="40">
  <rect width="40" height="40" rx="6" fill="#0d0d0d"/>
  <text x="50%" y="54%" dominant-baseline="middle" text-anchor="middle"
        font-family="'SF Mono', 'Fira Code', 'Cascadia Code', monospace"
        font-size="18" font-weight="700" fill="#c75c2c">&gt;_</text>
</svg>
```

- [ ] **Step 2: Update App.jsx header branding**

In `frontend/src/App.jsx`, replace the header logo block (lines 22-29):

```jsx
            <div className="w-7 h-7 rounded bg-[#00ff41]/20 border border-[#00ff41]/40 flex items-center justify-center">
              <span className="text-[#00ff41] text-sm font-bold">F</span>
            </div>
            <span className="text-sm font-bold text-[#00ff41] tracking-widest uppercase"
                  style={{ animation: 'glitch 3s infinite' }}>
              Felix
            </span>
```

With:

```jsx
            <img src="/felix-logo.svg" alt="Felix" className="w-7 h-7" />
            <span className="text-sm font-bold text-[#c75c2c] tracking-widest uppercase">
              Felix
            </span>
```

- [ ] **Step 3: Verify logo and header**

```bash
cat ~/Projects/felix/frontend/public/felix-logo.svg
grep "felix-logo" ~/Projects/felix/frontend/src/App.jsx
```

Expected: SVG file exists with `>_` text in #c75c2c, App.jsx references the logo image.

- [ ] **Step 4: Commit**

```bash
cd ~/Projects/felix
git add frontend/public/felix-logo.svg frontend/src/App.jsx
git commit -m "feat: add felix brand mark logo and update header"
```

---

### Task 5: Create docker-compose.yml

**Files:**
- Create: `docker-compose.yml`

- [ ] **Step 1: Write docker-compose.yml**

Write `docker-compose.yml` at the repo root:

```yaml
services:
  # ─── Database ──────────────────────────────────────────────────

  felix-postgres:
    image: pgvector/pgvector:pg16
    platform: linux/amd64
    restart: unless-stopped
    environment:
      POSTGRES_USER: ${POSTGRES_USER:-felix}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?Set POSTGRES_PASSWORD in .env}
      POSTGRES_DB: ${POSTGRES_DB:-felix}
    volumes:
      - ./backend/pgdata:/var/lib/postgresql/data
      - ./backend/init.sql:/docker-entrypoint-initdb.d/init.sql:ro
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-felix} -d ${POSTGRES_DB:-felix}"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 30s
    networks:
      - felix

  # ─── Search API ────────────────────────────────────────────────

  felix-api:
    build:
      context: ./backend
      dockerfile: Dockerfile.search
    platform: linux/amd64
    restart: unless-stopped
    depends_on:
      felix-postgres:
        condition: service_healthy
    environment:
      POSTGRES_HOST: felix-postgres
      POSTGRES_PORT: 5432
      POSTGRES_USER: ${POSTGRES_USER:-felix}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB:-felix}
      AZURE_OPENAI_ENDPOINT: ${AZURE_OPENAI_ENDPOINT}
      AZURE_OPENAI_API_KEY: ${AZURE_OPENAI_API_KEY}
      AZURE_OPENAI_API_VERSION: ${AZURE_OPENAI_API_VERSION:-2024-02-01}
      AZURE_OPENAI_EMBEDDING_MODEL: ${AZURE_OPENAI_EMBEDDING_MODEL:-text-embedding-3-small}
      IMAGES_PATH: /images
      INGEST_PATH: /ingest
    volumes:
      - ~/mission-control-images:/images:ro
      - ~/mission-control-ingest:/ingest
    ports:
      - "127.0.0.1:8001:8001"
    networks:
      - felix

  # ─── Ingestion Worker ─────────────────────────────────────────

  felix-ingestion:
    build:
      context: ./backend
      dockerfile: Dockerfile
    platform: linux/amd64
    restart: unless-stopped
    depends_on:
      felix-postgres:
        condition: service_healthy
    environment:
      POSTGRES_HOST: felix-postgres
      POSTGRES_PORT: 5432
      POSTGRES_USER: ${POSTGRES_USER:-felix}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB:-felix}
      AZURE_OPENAI_ENDPOINT: ${AZURE_OPENAI_ENDPOINT}
      AZURE_OPENAI_API_KEY: ${AZURE_OPENAI_API_KEY}
      AZURE_OPENAI_API_VERSION: ${AZURE_OPENAI_API_VERSION:-2024-02-01}
      AZURE_OPENAI_EMBEDDING_MODEL: ${AZURE_OPENAI_EMBEDDING_MODEL:-text-embedding-3-small}
      INGEST_PATH: /ingest
      IMAGES_PATH: /images
      CHUNK_SIZE: ${CHUNK_SIZE:-500}
      CHUNK_OVERLAP: ${CHUNK_OVERLAP:-50}
      ENABLE_CODE_ENRICHMENT: ${ENABLE_CODE_ENRICHMENT:-true}
      ENABLE_FORMULA_ENRICHMENT: ${ENABLE_FORMULA_ENRICHMENT:-true}
      ENABLE_PICTURE_DESCRIPTION: ${ENABLE_PICTURE_DESCRIPTION:-false}
      ENABLE_PICTURE_CLASSIFICATION: ${ENABLE_PICTURE_CLASSIFICATION:-false}
      ENABLE_GPU_CONVERSION: ${ENABLE_GPU_CONVERSION:-false}
      GPU_CONVERT_ENDPOINT: ${GPU_CONVERT_ENDPOINT:-http://felix-gpu:8080}
      GPU_CONVERT_API_KEY: ${GPU_CONVERT_API_KEY:-}
    volumes:
      - ~/mission-control-ingest:/ingest:ro
      - ~/mission-control-images:/images
      - docling-models:/home/appuser/.cache
    networks:
      - felix

  # ─── Frontend ──────────────────────────────────────────────────

  felix-frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    platform: linux/amd64
    restart: unless-stopped
    depends_on:
      - felix-api
    ports:
      - "127.0.0.1:5180:5180"
    networks:
      - felix

  # ─── GPU Conversion (optional) ────────────────────────────────

  felix-gpu:
    build:
      context: ./backend
      dockerfile: Dockerfile.gpu
    restart: unless-stopped
    profiles: ["gpu"]
    ports:
      - "127.0.0.1:8080:8080"
    environment:
      API_KEY: ${GPU_CONVERT_API_KEY:-}
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
    networks:
      - felix

volumes:
  docling-models:

networks:
  felix:
```

- [ ] **Step 2: Validate YAML syntax**

```bash
cd ~/Projects/felix
docker compose config --quiet 2>&1 || echo "YAML invalid"
```

Expected: no output (valid YAML) or warnings about unset env vars (acceptable).

- [ ] **Step 3: Commit**

```bash
cd ~/Projects/felix
git add docker-compose.yml
git commit -m "feat: add standalone docker-compose with felix network"
```

---

### Task 6: Create .env.example, .gitignore, LICENSE

**Files:**
- Create: `.env.example`
- Create: `.gitignore`
- Create: `LICENSE`

- [ ] **Step 1: Create .env.example**

Write `.env.example`:

```bash
# ─── PostgreSQL ──────────────────────────────────────────────────
POSTGRES_USER=felix
POSTGRES_PASSWORD=changeme
POSTGRES_DB=felix

# ─── Azure OpenAI ────────────────────────────────────────────────
AZURE_OPENAI_API_KEY=
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_API_VERSION=2024-02-01
AZURE_OPENAI_EMBEDDING_MODEL=text-embedding-3-small

# ─── Ingestion Options ──────────────────────────────────────────
CHUNK_SIZE=500
CHUNK_OVERLAP=50
ENABLE_CODE_ENRICHMENT=true
ENABLE_FORMULA_ENRICHMENT=true
ENABLE_PICTURE_DESCRIPTION=false
ENABLE_PICTURE_CLASSIFICATION=false

# ─── GPU Conversion (optional, requires NVIDIA GPU) ─────────────
ENABLE_GPU_CONVERSION=false
GPU_CONVERT_ENDPOINT=http://felix-gpu:8080
GPU_CONVERT_API_KEY=

# ─── Frontend ───────────────────────────────────────────────────
VITE_API_URL=/api
```

- [ ] **Step 2: Create .gitignore**

Write `.gitignore`:

```gitignore
# Python
__pycache__/
*.pyc
*.pyo
.venv/
*.egg-info/

# Node
node_modules/
dist/

# Docker
backend/pgdata/

# Environment
.env

# IDE
.vscode/
.idea/

# OS
.DS_Store
```

- [ ] **Step 3: Create LICENSE**

Write `LICENSE`:

```
MIT License

Copyright (c) 2026 datagobes

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

- [ ] **Step 4: Commit**

```bash
cd ~/Projects/felix
git add .env.example .gitignore LICENSE
git commit -m "feat: add .env.example, .gitignore, and MIT license"
```

---

### Task 7: Create documentation (CONTEXT.md, RESEARCH.md, DECISIONS.md)

**Files:**
- Create: `docs/CONTEXT.md`
- Create: `docs/RESEARCH.md`
- Create: `docs/DECISIONS.md`

- [ ] **Step 1: Create docs/CONTEXT.md**

Write `docs/CONTEXT.md`:

```markdown
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
```

- [ ] **Step 2: Create docs/RESEARCH.md**

Write `docs/RESEARCH.md`:

```markdown
# Felix — Research Notes

Research findings and explorations related to Felix development.
```

- [ ] **Step 3: Create docs/DECISIONS.md**

Write `docs/DECISIONS.md`:

```markdown
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
```

- [ ] **Step 4: Commit**

```bash
cd ~/Projects/felix
git add docs/
git commit -m "docs: add CONTEXT.md, RESEARCH.md, and DECISIONS.md"
```

---

### Task 8: Create README.md

**Files:**
- Create: `README.md`

- [ ] **Step 1: Write README.md**

Write `README.md`:

```markdown
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

- Frontend: [http://localhost:5180](http://localhost:5180)
- API: [http://localhost:8001/health](http://localhost:8001/health)

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
```

- [ ] **Step 2: Commit**

```bash
cd ~/Projects/felix
git add README.md
git commit -m "docs: add README with architecture, features, and quick start"
```

---

### Task 9: Create CLAUDE.md

**Files:**
- Create: `CLAUDE.md`

- [ ] **Step 1: Write CLAUDE.md**

Write `CLAUDE.md`:

```markdown
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
```

- [ ] **Step 2: Commit**

```bash
cd ~/Projects/felix
git add CLAUDE.md
git commit -m "docs: add CLAUDE.md with project instructions"
```

---

### Task 10: Remove ROADMAP.md and clean up

**Files:**
- Delete: `ROADMAP.md` (if present — was untracked at session start)
- Delete: `docs/superpowers/` (brainstorming artifacts, not needed in final repo)

- [ ] **Step 1: Remove brainstorming artifacts**

```bash
cd ~/Projects/felix
rm -f ROADMAP.md
rm -rf docs/superpowers/
```

- [ ] **Step 2: Verify final structure**

```bash
cd ~/Projects/felix
find . -not -path './.git/*' -not -path './backend/pgdata/*' -not -name '.git' | sort
```

Expected: the complete file tree matching the spec.

- [ ] **Step 3: Commit**

```bash
cd ~/Projects/felix
git add -A
git commit -m "chore: clean up planning artifacts"
```

---

### Task 11: Verification — build and basic checks

- [ ] **Step 1: Validate docker compose config**

```bash
cd ~/Projects/felix
docker compose config --quiet
```

Expected: no errors.

- [ ] **Step 2: Build all images**

```bash
cd ~/Projects/felix
docker compose build
```

Expected: all four images build successfully (felix-postgres is a pull, not a build).

- [ ] **Step 3: Start services**

```bash
cd ~/Projects/felix
docker compose up -d
```

Expected: felix-postgres, felix-api, felix-ingestion, felix-frontend all start.

- [ ] **Step 4: Check service health**

```bash
docker compose ps
curl -s http://localhost:8001/health | head -c 200
curl -s -o /dev/null -w "%{http_code}" http://localhost:5180
```

Expected: all services running, API returns health JSON, frontend returns 200.

- [ ] **Step 5: Verify frontend loads with correct branding**

Open http://localhost:5180 in browser. Verify:
- Felix logo (>_ in ember orange) appears in header
- Felix logo appears as favicon
- "Felix" wordmark next to logo
- No errors in browser console

- [ ] **Step 6: Stop services**

```bash
docker compose down
```

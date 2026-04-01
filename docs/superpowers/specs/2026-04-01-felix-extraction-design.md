# Felix — Standalone Repository Extraction Design

## Overview

Extract the document intelligence platform from `alfred-planning/mission-control/` into a standalone `felix` repository. One-time direct copy + transform, single commit.

## Source → Target File Mapping

### Backend (`rag/` → `backend/`)

| Source | Target | Changes |
|--------|--------|---------|
| `ingestion.py` | `ingestion.py` | None |
| `search.py` | `search.py` | None |
| `gpu_convert_service.py` | `gpu_convert_service.py` | None |
| `init.sql` | `init.sql` | Append `ingestion_jobs` table from `dashboard/migrations/001_ingestion_jobs.sql` |
| `Dockerfile` | `Dockerfile` | None |
| `Dockerfile.search` | `Dockerfile.search` | None |
| `Dockerfile.gpu` | `Dockerfile.gpu` | None |
| `requirements.txt` | `requirements.txt` | None |
| `requirements.search.txt` | `requirements.search.txt` | None |
| `requirements.gpu.txt` | `requirements.gpu.txt` | None |
| `conftest.py` | `conftest.py` | None |
| `test_ingestion.py` | `test_ingestion.py` | None |
| `test_search.py` | `test_search.py` | None |
| `pytest.ini` | `pytest.ini` | None |
| `requirements.test.txt` | `requirements.test.txt` | None |

**Excluded:** `host-instructions.md`, `com.missioncontrol.rsync.plist`, `README.md`

### Frontend (`dashboard/` → `frontend/`)

| Source | Target | Changes |
|--------|--------|---------|
| `src/` (entire tree) | `src/` | None (except `api/client.jsx`) |
| `src/api/client.jsx` | `src/api/client.jsx` | Replace `VITE_RAG_URL` + `VITE_METRICS_URL` → single `VITE_API_URL` |
| `index.html` | `index.html` | Update title to "Felix", replace Vite favicon with `felix-logo.svg` |
| `package.json` | `package.json` | None |
| `vite.config.js` | `vite.config.js` | None |
| `tailwind.config.js` | `tailwind.config.js` | None |
| `postcss.config.js` | `postcss.config.js` | None |
| `components.json` | `components.json` | None |
| `jsconfig.json` | `jsconfig.json` | None |
| `eslint.config.js` | `eslint.config.js` | None |
| `Dockerfile` | `Dockerfile` | None |
| `nginx.conf` | `nginx.conf` | Update upstream names (`rag-search` → `felix-api`), remove metrics proxy |
| — | `public/felix-logo.svg` | New: dark rect (#0d0d0d) + ember orange (#c75c2c) `>_` monospace text |

**Excluded:** `vm-patches/`, `patches/`, `docker-compose.dashboard.yml`, `migrations/`, `package-lock.json`, `public/vite.svg`

### Frontend header branding

Update `App.jsx` to show `felix-logo.svg` + "Felix" wordmark in the header, replacing existing branding.

## Docker Compose

Five services on standalone `felix` network. All services use `platform: linux/amd64`.

| Service | Build/Image | Ports | Profile | Notes |
|---------|-------------|-------|---------|-------|
| `felix-postgres` | `pgvector/pgvector:pg16` | internal 5432 | default | Mounts `init.sql`, data in `./backend/pgdata` |
| `felix-api` | `backend/Dockerfile.search` | `127.0.0.1:8001` | default | FastAPI search/chat API |
| `felix-ingestion` | `backend/Dockerfile` | none | default | Ingestion worker with GPU env vars |
| `felix-frontend` | `frontend/Dockerfile` | `127.0.0.1:5180` | default | Nginx + React SPA |
| `felix-gpu` | `backend/Dockerfile.gpu` | `127.0.0.1:8080` | `gpu` | NVIDIA runtime, optional |

**Removed from source:** `openclaw_default` network, `metrics` service.

### Ingestion GPU env vars

```yaml
ENABLE_GPU_CONVERSION: ${ENABLE_GPU_CONVERSION:-false}
GPU_CONVERT_ENDPOINT: ${GPU_CONVERT_ENDPOINT:-http://felix-gpu:8080}
GPU_CONVERT_API_KEY: ${GPU_CONVERT_API_KEY:-}
```

## New Files

### `.env.example`

```
POSTGRES_PASSWORD=
AZURE_OPENAI_API_KEY=
AZURE_OPENAI_ENDPOINT=
AZURE_OPENAI_EMBEDDING_DEPLOYMENT=
ENABLE_GPU_CONVERSION=false
GPU_CONVERT_ENDPOINT=http://felix-gpu:8080
GPU_CONVERT_API_KEY=
VITE_API_URL=/api
```

### `felix-logo.svg`

SVG with dark rounded rect background (#0d0d0d, rx=6), ember orange (#c75c2c) monospace `>_` text centered. Used as favicon and header logo.

### Documentation

- `docs/CONTEXT.md` — project context (as specified in task)
- `docs/RESEARCH.md` — empty placeholder
- `docs/DECISIONS.md` — expanded key decisions with rationale
- `README.md` — professional README with architecture diagram, features, quick start, tech stack
- `CLAUDE.md` — project-level Claude Code instructions
- `LICENSE` — MIT

### `.gitignore`

Python (`__pycache__/`, `*.pyc`, `.venv/`), Node (`node_modules/`, `dist/`), Docker (`pgdata/`), environment (`.env`).

## Verification Plan

1. `docker compose build` — all images build
2. `docker compose up -d` — services start (CPU-only)
3. `docker compose --profile gpu up -d` — starts with GPU service (NVIDIA required)
4. Frontend at `localhost:5180`
5. API health at `localhost:8001/health`
6. Upload test document → ingestion completes → search returns results
7. Logo visible in header and favicon

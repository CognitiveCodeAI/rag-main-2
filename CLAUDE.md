# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

NPR (Near-Perfect RAG) is a production-grade Retrieval-Augmented Generation system for document question answering with evidence-based citations. It uses a graph-based document model: documents are parsed into pages, chunked, then represented as nodes and edges in a graph structure stored across PostgreSQL (metadata/graph), Milvus (vector embeddings), and MinIO (document storage).

## Architecture

**Monorepo with two services:**
- `backend/` — Python FastAPI API server (port 8000)
- `frontend/` — Next.js 16 + React 19 app (port 3000)

**Infrastructure (via docker-compose):** PostgreSQL, Milvus (+ etcd + minio-milvus), MinIO, Redis

### Backend Key Modules

- `backend/main.py` — FastAPI app setup, lifespan, health check, route mounting
- `backend/app/config.py` — Pydantic `BaseSettings`, all config via env vars / `.env`
- `backend/app/routes/` — API endpoints (`qa.py`, `ingest.py`, `documents.py`, `retrieve.py`, `embed.py`, `prompts.py`, `acl.py`, `settings.py`)
- `backend/app/graph/pipeline.py` — **Ingestion pipeline orchestrator**: doc registration, page extraction, OCR fallback, chunking, node/edge creation, vector embedding, DB persistence
- `backend/app/qa/runner.py` — **QA pipeline orchestrator**: query normalization, vector search, graph expansion, reranking, context packing, LLM answer generation with citations, conflict detection
- `backend/app/db/models.py` — SQLAlchemy ORM models (Document, IngestJob, Chunk, DocumentIR)
- `backend/app/db/graph_models.py` — Graph ORM models (DocumentGraph, Node, Edge)
- `backend/app/parsers/` — Document parsers (PDF, DOCX, HTML, Markdown, CSV, XLSX, text)
- `backend/app/tasks/` — Celery background tasks for async ingestion/embedding
- `backend/app/prompts/` — Versioned prompt templates (v1/v2) for QA, OCR, reranking, verification
- `backend/app/acl/` — **Access Control Layer**: multi-tenant authorization (`enforcer`, `policy`, `resolver`, `postgres_filter`, `audit`). Feature-flagged via `ACL_ENABLED` (default off). Enforces tenant/role visibility on documents and QA results, with row-level Postgres filtering and an audit trail.
- `backend/app/monitor/` — Active self-healing monitor (`observer`, `checks`, `remediation`, `state`). Runs as an optional daemon (`./dev monitor`) that watches service health and auto-remediates. Writes JSONL logs.
- `backend/app/vectordb/milvus_client.py` — Milvus wrapper (the active vector store; `opensearch-py`/`neo4j` deps exist for optional/experimental backends)
- `backend/app/llm/openai_client.py` — OpenAI GPT client for QA answer generation
- `backend/app/embeddings/` — OpenAI embedding client + vector record schema
- `backend/app/ocr/` — OCR clients: `openai_client.py` (default) and `ollama_client.py` (alternate)

### Frontend Key Modules

- `frontend/src/app/(app)/` — App Router pages (dashboard, chat, documents, search, inspect, prompts, settings)
- `frontend/src/lib/api.ts` — API client with all TypeScript types and fetch functions
- `frontend/src/components/ui/` — Shadcn/ui component library (Radix UI + Tailwind CSS 4)
- `frontend/src/components/layout/` — App shell (sidebar, header, command menu with Cmd+K)
- State management: TanStack React Query for server state, React Hook Form for forms, next-themes for dark mode

### Data Flow

1. **Ingestion**: Upload → Parser → Pages → Chunker → Nodes + Edges → OpenAI embeddings → Milvus + PostgreSQL + MinIO
2. **QA**: Question → Embedding → Milvus vector search → Graph expansion → Context packing → LLM generation → Cited answer

## Common Commands

### `./dev` — unified dev CLI (preferred entry point)
A single Bash wrapper that orchestrates Docker, env, migrations, and all services. Prefer it over the lower-level commands below.
```bash
./dev init          # Validate prerequisites and bootstrap backend/.env
./dev up            # Start full local environment (infra + backend + celery + frontend); --seed to seed data
./dev down          # Stop local infrastructure
./dev status        # Show service + endpoint status
./dev logs <target> # Tail logs: app|infra|backend|frontend|celery|monitor
./dev migrate       # Run Alembic database migrations
./dev test          # Run backend test suite (and frontend tests if configured)
./dev monitor       # Run the active self-healing monitor (--daemon | --status | --stop)
./dev doctor        # Diagnose local environment issues
./dev reset         # Reset local dev env (--volumes wipes data); asks for confirmation
```

### Infrastructure
```bash
docker-compose up -d          # Start PostgreSQL, Milvus, MinIO, Redis
docker-compose down           # Stop all infrastructure
docker-compose down -v        # Stop and delete all data (full reset)
```

### Backend
```bash
cd backend
.\venv\Scripts\activate                                           # Activate venv (Windows)
source venv/bin/activate                                          # Activate venv (Linux/macOS)
uvicorn main:app --reload --host 0.0.0.0 --port 8000              # Dev server
celery -A app.worker worker --loglevel=info --pool=prefork --concurrency=4  # Linux/macOS Celery worker (Windows: --pool=solo)
python -m scripts.setup.setup_all                                 # Initialize DBs (first time)
pytest                                                            # Run all tests
pytest tests/qa/ -v                                               # QA tests only
pytest tests/test_routes.py::test_health -v                       # Run a single test
pytest --cov=app tests/                                           # Tests with coverage
```

### Frontend
```bash
cd frontend
npm run dev       # Dev server at localhost:3000
npm run build     # Production build
npm run lint      # ESLint
```

### All Services
```bash
python run.py                  # Start backend + Celery worker + frontend (Ctrl+C to stop)
python run.py --no-celery      # Start without Celery worker
python run.py --force-cleanup  # Kill existing processes on ports 3000/8000 first
```

### First-Time Setup
```bash
.\setup.ps1                    # Windows (PowerShell)
./setup.sh                     # Linux/macOS
```
The setup scripts handle Docker containers, Python venv, Node dependencies, database migrations, and connection verification.

### Verified local-run notes (macOS, confirmed 2026-06)
These were observed end-to-end while bringing the stack up locally:
- **Python: build the venv with `python3.12`.** The pinned deps (pymilvus 2.4.9, pydantic, etc.) lack wheels for Python 3.13/3.14; 3.12 installs cleanly. Node ≥ 20.9 is required by Next 16 (Node 24 works).
- **`setuptools<81` is required** (now pinned in `requirements.txt`): setuptools ≥ 81 removed `pkg_resources`, which `pymilvus` imports at startup.
- **Run the Celery worker with `--pool=solo` on macOS.** The default `--pool=prefork` crashes (`fork()` + Obj-C `NSCharacterSet` → SIGABRT, then native libs SIGSEGV), leaving every ingest stuck `pending`. `solo` runs in-process and works. (`how_to_run.txt` already flags solo as required on Windows.)
- **Running migrations directly requires the venv on `PATH`** — `scripts.setup.setup_postgres` shells out to the `alembic` CLI: `PATH="$PWD/venv/bin:$PATH" python -m scripts.setup.setup_postgres`. The `./dev migrate` wrapper handles this for you.
- **Ingestion does not embed.** `POST /v1/ingest/document` persists graph nodes to Postgres only; you must then call `POST /v1/embed/document` (or `scripts/embed_all.py`) to populate Milvus before `POST /v1/qa/ask` returns hits.
- **QA `doc_id` filter expects the canonical graph doc id**, not the upload `doc_id`. Omit `doc_id` to search all documents, or pass the `graph_doc_id` returned by the ingest task.
- `pytest`/`pytest-asyncio` are test-only deps not in `requirements.txt`; install them into the venv to run the suite. Default `pytest` run is unit-only (integration tests are skipped unless `RUN_INTEGRATION_TESTS=1`).

## Configuration

Backend config is in `backend/app/config.py` via Pydantic `BaseSettings`. All values come from environment variables or `backend/.env`. Defaults match `docker-compose.yml` for local dev.

**Required env var:** `OPENAI_API_KEY` — used for embeddings (`text-embedding-3-large`, 3072-dim), QA answer generation (`llm/openai_client.py`, default `gpt-5.2`), and the default OCR provider (`gpt-5-mini`). Frontend uses `NEXT_PUBLIC_API_URL` (defaults to `http://localhost:8000`).

> Note: `config.py` carries an `llm_model: "llama3.2"` default, but the QA path calls the OpenAI Chat Completions API directly — answer generation is OpenAI-backed, not Ollama.

**ACL:** Disabled by default (`ACL_ENABLED=false`) — authorization checks are bypassed until enabled. When on, `ACL_STRICT_MODE` fails closed on missing entitlements and `ACL_DISCLOSURE_MODE` selects `opaque` (404) vs `explicit` (403) for denied access.

**Database migrations:** Managed by Alembic (`backend/alembic/`). Run via `./dev migrate` or `alembic upgrade head` from `backend/`.

## API Endpoints

All backend routes are prefixed with `/v1/`:
- `POST /v1/ingest/document` — Upload and process a document
- `POST /v1/qa/ask` — Ask a question against ingested documents
- `POST /v1/retrieve/vector` — Vector similarity search
- `GET /v1/documents` — List documents
- `GET /health` — Health check (`?check_services=true` for full connectivity test)
- Interactive docs at `http://localhost:8000/docs`

## Key Design Decisions

- **Page-bounded chunking**: Chunks never cross page boundaries, enabling precise page-number citations
- **Graph RAG**: Nodes (chunks, figures) connected by edges (adjacency, references, explained_by) allow expansion beyond vector-search hits
- **Idempotent ingestion**: Content-hash deduplication prevents duplicate processing
- **OCR fallback**: Pages with low text-quality scores (< 0.3 threshold) automatically fall back to OCR. Provider is set by `OCR_PROVIDER` — `openai` (default, `gpt-5-mini` vision) or `ollama` (`deepseek-ocr`, local)
- **Versioned prompts**: Prompt templates in `backend/app/prompts/` use `_v1`/`_v2` suffixes for iteration without breaking existing behavior
- **ACL is enforced at retrieval, not just routes**: When enabled, authorization filters Postgres rows and QA candidates by tenant/role so denied content never reaches the LLM context — not merely hidden at the API boundary
- **Two MinIO instances in docker-compose**: One for Milvus internal storage (port 9010), one for application document storage (port 9000)
- **Docling backend (optional)**: Enable `DOCLING_ENABLED_DEFAULT=true` in `.env` to use Docling for multi-format document conversion (PDF, DOCX, PPTX, XLSX). Requires `pip install docling>=2.72.0`

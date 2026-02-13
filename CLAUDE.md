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
- `backend/app/routes/` — API endpoints (`qa.py`, `ingest.py`, `documents.py`, `retrieve.py`, `embed.py`, `prompts.py`)
- `backend/app/graph/pipeline.py` — **Ingestion pipeline orchestrator**: doc registration, page extraction, OCR fallback, chunking, node/edge creation, vector embedding, DB persistence
- `backend/app/qa/runner.py` — **QA pipeline orchestrator**: query normalization, vector search, graph expansion, reranking, context packing, LLM answer generation with citations, conflict detection
- `backend/app/db/models.py` — SQLAlchemy ORM models (Document, IngestJob, Chunk, DocumentIR)
- `backend/app/db/graph_models.py` — Graph ORM models (DocumentGraph, Node, Edge)
- `backend/app/parsers/` — Document parsers (PDF, DOCX, HTML, Markdown, CSV, XLSX, text)
- `backend/app/tasks/` — Celery background tasks for async ingestion/embedding
- `backend/app/prompts/` — Versioned prompt templates (v1/v2) for QA, OCR, reranking, verification

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

## Configuration

Backend config is in `backend/app/config.py` via Pydantic `BaseSettings`. All values come from environment variables or `backend/.env`. Defaults match `docker-compose.yml` for local dev.

**Required env var:** `OPENAI_API_KEY` (for embeddings). Frontend uses `NEXT_PUBLIC_API_URL` (defaults to `http://localhost:8000`).

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
- **OCR fallback**: Pages with low text-quality scores (< 0.3 threshold) automatically fall back to Ollama-based OCR
- **Versioned prompts**: Prompt templates in `backend/app/prompts/` use `_v1`/`_v2` suffixes for iteration without breaking existing behavior
- **Two MinIO instances in docker-compose**: One for Milvus internal storage (port 9010), one for application document storage (port 9000)
- **Docling backend (optional)**: Enable `DOCLING_ENABLED_DEFAULT=true` in `.env` to use Docling for multi-format document conversion (PDF, DOCX, PPTX, XLSX). Requires `pip install docling>=2.72.0`

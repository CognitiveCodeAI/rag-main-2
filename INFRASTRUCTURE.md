# NPR Infrastructure Reference

> **Single source of truth** for all service connections, credentials, and configuration.
> Last verified: 2026-02-09. All values pulled from running systems and source code.

---

## Network Overview

All backend infrastructure runs on a single Ubuntu server. The application
(FastAPI, Celery, Frontend) runs on the Windows development machine.

| Role | Host | OS |
|------|------|----|
| **Infrastructure server** | `192.168.100.25` | Ubuntu 22.04, Linux 6.8.0-90-generic x86_64 |
| **Application machine** | `192.168.0.82` (LAN) / `localhost` | Windows 11 10.0.26200 |

---

## 1. PostgreSQL

| Property | Value |
|----------|-------|
| **Host** | `192.168.100.25` |
| **Port** | `5433` |
| **Database** | `appdb` |
| **User** | `appuser` |
| **Password** | `1Shot@OneKill` |
| **Version** | PostgreSQL 14.20 (Ubuntu 14.20-0ubuntu0.22.04.1) |
| **Deployment** | Standalone (not Docker) |

**Connection string:**
```
postgresql://appuser:1Shot%40OneKill@192.168.100.25:5433/appdb
```

**How the app connects:** `backend/app/db/session.py` reads `DB_HOST`, `DB_PORT`,
`DB_NAME`, `DB_USER`, `DB_PASSWORD` from environment (loaded from `backend/.env`).
Falls back to hardcoded defaults that match production values. Uses SQLAlchemy with
`pool_size=5`, `max_overflow=10`, `pool_pre_ping=True`.

**Session behavior:**
- `get_session()` (FastAPI dependency): does NOT auto-commit. Routes that write
  data must call `db.commit()` explicitly.
- `session_scope()` (context manager): auto-commits on success, rolls back on exception.

**Schema version:** Alembic migration `007` (migrations in `backend/alembic/versions/`).

**Application tables:**

| Table | Purpose | Key columns |
|-------|---------|-------------|
| `documents_graph` | Document metadata, ACL | `doc_id` (PK, VARCHAR 64), `source_uri`, `content_hash`, `version`, `visibility`, `tenant_id` |
| `nodes` | Graph nodes (chunks, figures, tables) | `node_id` (PK, VARCHAR 64), `doc_id` (FK), `node_type`, `page_no`, `text_md`, `text_plain` |
| `edges` | Graph edges (adjacency, references) | `id` (PK, serial), `from_node_id`, `to_node_id`, `edge_type`, `doc_id` |
| `ingest_jobs` | Ingestion job tracking | `job_id` (PK, UUID), `doc_id`, `status`, `pipeline_stage`, `error` |
| `embedding_jobs` | Embedding job tracking | `job_id` (PK, UUID), `doc_id`, `version_id`, `status`, `pipeline_stage`, `chunk_count`, `total_tokens` |
| `content_registry` | Duplicate detection | `content_hash` (PK), `canonical_doc_id`, `alias_count` |
| `alembic_version` | Migration tracking | `version_num` |

**Note:** This database is shared with other applications (n8n, etc.) — there are
~70 tables total. The `ingest_jobs` table has some duplicate column names from
overlapping migrations between applications. Our application tables are the 7
listed above.

**Env vars** (in `backend/.env`):
```
DB_HOST=192.168.100.25
DB_PORT=5433
DB_NAME=appdb
DB_USER=appuser
DB_PASSWORD=1Shot@OneKill
```

---

## 2. Redis

| Property | Value |
|----------|-------|
| **Host** | `192.168.100.25` |
| **Port** | `6379` |
| **Version** | 7.4.7 |
| **Mode** | Standalone |
| **Deployment** | Docker container |
| **Persistence** | AOF (append-only file) |

**Databases used:**
- `db0` — Celery broker (task queue)
- `db1` — Celery result backend (task results)

**Connection URLs:**
```
redis://192.168.100.25:6379/0   (broker)
redis://192.168.100.25:6379/1   (results)
```

**How the app connects:** Two paths, both read `REDIS_URL` / `REDIS_BACKEND` from
environment:
1. `backend/app/worker.py` — reads `os.getenv("REDIS_URL")` and
   `os.getenv("REDIS_BACKEND")` at import time. Falls back to `redis://localhost:6379/0`
   if env vars are not set.
2. `backend/app/config.py` — `Settings.redis_url` and `Settings.redis_backend` via
   Pydantic BaseSettings (also falls back to localhost).

**Critical:** The Celery worker MUST be started with the `.env` loaded, otherwise
it defaults to `localhost:6379` and connects to the wrong Redis. The `run.py`
launcher handles this via `load_backend_env()`. If starting Celery manually, you
must ensure the env vars are set.

**Env vars** (in `backend/.env`):
```
REDIS_URL=redis://192.168.100.25:6379/0
REDIS_BACKEND=redis://192.168.100.25:6379/1
```

---

## 3. MinIO (Object Storage)

| Property | Value |
|----------|-------|
| **Host** | `192.168.100.25` |
| **Port** | `9000` (API) |
| **Access Key** | `admin` |
| **Secret Key** | `!1Shot@OneKill!` |
| **Deployment** | Docker container |
| **Secure** | `false` (HTTP, not HTTPS) |

**Buckets:**

| Bucket | Purpose |
|--------|---------|
| `npr-corpus` | All document artifacts |
| `npr-traces` | QA flight recorder logs |

**Object layout in `npr-corpus`:**
```
raw/{doc_id}/{version_id}/{filename}          # Original uploaded file
ir/{doc_id}/{version_id}/document_ir.json     # Parsed intermediate representation
chunks/{doc_id}/{version_id}/chunks.jsonl     # Chunked text records
embeddings/{doc_id}/{version_id}/bundle.json  # Embedding bundles (future)
```

**How the app connects:** `backend/app/storage/minio_client.py` reads
`MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY` from environment.
Falls back to hardcoded defaults that match production values.

**Env vars** (in `backend/.env`):
```
MINIO_ENDPOINT=192.168.100.25:9000
MINIO_ACCESS_KEY=admin
MINIO_SECRET_KEY=!1Shot@OneKill!
```

---

## 4. Milvus (Vector Database)

| Property | Value |
|----------|-------|
| **Host** | `192.168.100.25` |
| **Port** | `19530` |
| **Version** | v2.3.16 |
| **Deployment** | Standalone systemd service (`/usr/bin/milvus run standalone`) |
| **Storage** | Local filesystem (`/var/lib/milvus/data/`) |
| **Config** | `/etc/milvus/configs/milvus.yaml` |
| **Embedded etcd** | `/default.etcd/` (root filesystem) |
| **RocksMQ** | `/var/lib/milvus/rdb_data/` and `rdb_data_meta_kv/` |

**Collections:**

| Collection | Purpose | Entities |
|------------|---------|----------|
| `graph_chunks_v2` | Text chunk embeddings | 967 |
| `graph_figures_v2` | Figure/image embeddings | 6 |
| `graph_tables_v2` | Table embeddings | 14 |

**Schema (identical for all 3 collections):**

| Field | Type | Notes |
|-------|------|-------|
| `node_id` | VARCHAR(64) | Primary key |
| `doc_id` | VARCHAR(64) | Document reference |
| `version` | INT32 | Document version |
| `page_no` | INT32 | Source page number |
| `vector` | FLOAT_VECTOR(3072) | OpenAI text-embedding-3-large |
| `year` | INT32 | Metadata filter |
| `doc_type` | VARCHAR(64) | Metadata filter |
| `department` | VARCHAR(64) | Metadata filter |
| `authority_tier` | INT32 | Metadata filter |

**Index:** `IVF_FLAT` on `vector` field, metric type `COSINE`.

**Recovery after power failure:** If Milvus hangs on `load()` or shows
"find no available rootcoord" errors, stop Milvus, move `rdb_data/` and
`rdb_data_meta_kv/`, then restart. This resets RocksMQ but preserves vector data.

**How the app connects:** `backend/app/config.py` reads `MILVUS_HOST` and
`MILVUS_PORT` via Pydantic BaseSettings. Uses `pymilvus` library.

**Env vars** (in `backend/.env`):
```
MILVUS_HOST=192.168.100.25
MILVUS_PORT=19530
```

---

## 5. Celery Worker

| Property | Value |
|----------|-------|
| **App name** | `npr` |
| **Config** | `backend/app/worker.py` |
| **Broker** | Redis db0 (`redis://192.168.100.25:6379/0`) |
| **Result backend** | Redis db1 (`redis://192.168.100.25:6379/1`) |
| **Pool** | `solo` (required on Windows) |
| **Concurrency** | 20 |
| **Task time limit** | 3600s (1 hour hard), 3000s (50 min soft) |
| **Serializer** | JSON |
| **Acks late** | `true` (task acknowledged after completion, not receipt) |
| **Reject on worker lost** | `true` |

**Registered tasks:**

| Task name | Module | Purpose |
|-----------|--------|---------|
| `app.tasks.ingest.ingest_document_task` | `backend/app/tasks/ingest.py` | Document ingestion pipeline |
| `embed_nodes_task` | `backend/app/tasks/embed_nodes.py` | Generate embeddings and index to Milvus |
| `app.tasks.embed.embed_chunks_task` | `backend/app/tasks/embed.py` | Legacy chunk embedding |
| `app.tasks.embed.embed_document_task` | `backend/app/tasks/embed.py` | Legacy document embedding |
| `app.tasks.index.index_vectors_task` | `backend/app/tasks/index.py` | Legacy vector indexing |

**How to start:**

Option 1 — Via `run.py` (recommended, loads `.env` automatically):
```bash
python run.py          # Starts FastAPI + Celery + Frontend
```

Option 2 — Manually (must load `.env` first):
```bash
cd backend
# PowerShell:
Get-Content .env | ForEach-Object { if ($_ -match '^([^#].+?)=(.*)$') { [System.Environment]::SetEnvironmentVariable($matches[1], $matches[2]) } }
.\venv\Scripts\celery.exe -A app.worker worker --loglevel=info --pool=solo

# Or use the venv Python with dotenv:
.\venv\Scripts\python.exe -c "from dotenv import load_dotenv; load_dotenv('.env')" && .\venv\Scripts\celery.exe -A app.worker worker --loglevel=info --pool=solo
```

**Critical:** If started without `.env` loaded, the worker defaults to
`redis://localhost:6379/0` and will NOT process any tasks dispatched by FastAPI
(which connects to `redis://192.168.100.25:6379/0`).

**Known issue:** On Windows, the Celery worker does not automatically recover from
a lost Redis connection (`ConnectionResetError: [WinError 10054]`). If the remote
Redis goes down temporarily, the worker dies silently and must be restarted manually.

---

## 6. OpenAI API

| Property | Value |
|----------|-------|
| **Provider** | OpenAI |
| **Embedding model** | `text-embedding-3-large` |
| **Embedding dimension** | 3072 |
| **Max batch size** | 2048 |
| **LLM rewrite model** | `gpt-4o-mini` (for multi-turn query rewriting) |
| **Normalization** | L2 (applied client-side) |

**How the app connects:** `backend/app/embeddings/client.py` reads `OPENAI_API_KEY`
from environment. Used by the embedding task for vectorizing document chunks.
Also used by `backend/app/qa/runner.py` for LLM answer generation.

**Env vars** (in `backend/.env`):
```
OPENAI_API_KEY=sk-proj-fl2eewI...  (truncated)
EMBEDDING_MODEL=text-embedding-3-large    (default, not in .env)
EMBEDDING_DIM=3072                        (default, not in .env)
ENABLE_LLM_QUERY_REWRITE=true
LLM_REWRITE_MODEL=gpt-4o-mini
```

---

## 7. FastAPI Backend

| Property | Value |
|----------|-------|
| **Host** | `0.0.0.0` (binds all interfaces) |
| **Port** | `8000` |
| **App** | `backend/main.py` → `main:app` |
| **Version** | `0.1.0` |
| **Working directory** | `C:\Apps\rag\backend` |
| **Python venv** | `C:\Apps\rag\backend\venv` |

**CORS origins** (from `.env`):
```
http://localhost:3000
http://127.0.0.1:3000
http://192.168.0.82:3000
```

**API routes:**

| Prefix | Module | Purpose |
|--------|--------|---------|
| `GET /health` | `main.py` | Health check (add `?check_services=true` for full test) |
| `POST /v1/ingest/document` | `routes/ingest.py` | Upload and ingest a document |
| `GET /v1/ingest/job/{id}` | `routes/ingest.py` | Poll ingest job status |
| `GET /v1/ingest/jobs` | `routes/ingest.py` | List ingest jobs |
| `POST /v1/embed/document` | `routes/embed.py` | Trigger embedding for a document |
| `GET /v1/embed/job/{id}` | `routes/embed.py` | Poll embed job status |
| `GET /v1/embed/jobs` | `routes/embed.py` | List embed jobs |
| `POST /v1/qa/ask` | `routes/qa.py` | Ask a question (RAG pipeline) |
| `POST /v1/retrieve/vector` | `routes/retrieve.py` | Direct vector search |
| `GET /v1/retrieve/collections` | `routes/retrieve.py` | Milvus collection stats |
| `GET /v1/documents` | `routes/documents.py` | List documents |
| `GET /v1/documents/{id}/nodes` | `routes/documents.py` | List nodes for a document |
| `GET /v1/prompts` | `routes/prompts.py` | List prompt templates |
| `GET/PUT /v1/acl/documents/{id}/policy` | `routes/acl.py` | Document ACL policy |
| `GET /docs` | (auto) | Swagger UI |

**How to start:**
```bash
cd backend
.\venv\Scripts\activate
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

---

## 8. Frontend (Next.js)

| Property | Value |
|----------|-------|
| **Framework** | Next.js 16 + React 19 |
| **Port** | `3000` |
| **Working directory** | `C:\Apps\rag\frontend` |
| **API URL** | `http://192.168.0.82:8000` (configured in `.env.local`) |
| **UI library** | Shadcn/ui (Radix UI + Tailwind CSS 4) |
| **State** | TanStack React Query |

**Config file:** `frontend/.env.local`
```
NEXT_PUBLIC_API_URL=http://192.168.0.82:8000
```

**Note:** `NEXT_PUBLIC_API_URL` defaults to `http://localhost:8000` if not set
(defined in `frontend/src/lib/api.ts`). The `.env.local` overrides this to use
the LAN IP so the frontend is accessible from other devices on the network.

**How to start:**
```bash
cd frontend
npm run dev
```

**Pages:**

| Route | Purpose |
|-------|---------|
| `/` | Dashboard |
| `/chat` | QA chat interface |
| `/documents` | Document browser with upload |
| `/search` | Vector search |
| `/inspect` | Node/edge inspector |
| `/processing` | Job monitoring (ingest + embed) |
| `/prompts` | Prompt template viewer |
| `/settings` | App settings |

---

## Quick Reference: All Connection Strings

```
PostgreSQL:  postgresql://appuser:1Shot%40OneKill@192.168.100.25:5433/appdb
Redis:       redis://192.168.100.25:6379/0  (broker)
             redis://192.168.100.25:6379/1  (results)
MinIO:       http://192.168.100.25:9000     (admin / !1Shot@OneKill!)
Milvus:      192.168.100.25:19530
OpenAI:      api.openai.com                 (key in .env)
FastAPI:     http://localhost:8000
Frontend:    http://localhost:3000
```

---

## Quick Reference: Start All Services

```bash
# From project root — starts everything:
python run.py

# Or individually:
cd backend && .\venv\Scripts\activate
uvicorn main:app --reload --host 0.0.0.0 --port 8000
celery -A app.worker worker --loglevel=info --pool=solo   # MUST have .env loaded
cd ..\frontend && npm run dev
```

---

## Quick Reference: Health Check

```bash
# Basic:
curl http://localhost:8000/health

# Full (tests all 4 backend services):
curl http://localhost:8000/health?check_services=true
```

---

## Config Files

| File | Purpose | Loaded by |
|------|---------|-----------|
| `backend/.env` | All backend config (DB, Redis, MinIO, Milvus, OpenAI, CORS, ACL) | Pydantic BaseSettings, `run.py` |
| `backend/app/config.py` | Settings class with defaults and validation | FastAPI at startup |
| `backend/app/worker.py` | Celery app creation (reads REDIS_URL from env) | Celery worker |
| `backend/app/db/session.py` | SQLAlchemy engine (reads DB_* from env) | All DB operations |
| `backend/app/storage/minio_client.py` | MinIO client (reads MINIO_* from env) | Ingestion pipeline |
| `backend/app/embeddings/client.py` | OpenAI client (reads OPENAI_API_KEY from env) | Embedding task |
| `frontend/.env.local` | Frontend API URL override | Next.js at build/dev |
| `docker-compose.yml` | Infrastructure service definitions (reference only) | Not used in production |

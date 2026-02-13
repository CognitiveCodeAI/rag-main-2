# NPR RAG — Setup Guide

## Quick Start

**Windows (PowerShell):**
```powershell
.\setup.ps1
```

**Linux / macOS:**
```bash
chmod +x setup.sh
./setup.sh
```

The script handles everything: Docker containers, Python venv, Node dependencies, database migrations, and connection verification. When it finishes, run the app with `python run.py`.

---

## Prerequisites

Install these before running the setup script:

| Tool | Minimum Version | Check |
|------|----------------|-------|
| [Docker Desktop](https://www.docker.com/products/docker-desktop/) | With `docker compose` (v2) | `docker compose version` |
| [Python](https://www.python.org/downloads/) | 3.10+ | `python --version` |
| [Node.js](https://nodejs.org/) | 18+ | `node --version` |
| npm | (comes with Node.js) | `npm --version` |
| OpenAI API key | — | [Get one here](https://platform.openai.com/api-keys) |

**Ports that must be free:** 5432 (PostgreSQL), 19530 (Milvus), 9000 (MinIO), 6379 (Redis), 8000 (Backend), 3000 (Frontend).

---

## What the Setup Script Does

1. **Check prerequisites** — Verifies Docker, Python, Node.js, and npm are installed and meet version requirements.
2. **Start infrastructure** — Runs `docker compose up -d` and waits for PostgreSQL, Milvus, MinIO, and Redis to become healthy (up to 3 minutes).
3. **Configure environment** — Copies `backend/.env.example` to `backend/.env` and prompts for your `OPENAI_API_KEY`.
4. **Create Python virtual environment** — Creates `backend/venv/` and installs all Python dependencies from `requirements.txt`.
5. **Run database setup** — Executes Alembic migrations (PostgreSQL), creates Milvus vector collections, and creates MinIO storage buckets.
6. **Install frontend dependencies** — Runs `npm install` in `frontend/`.
7. **Verify connections** — Tests connectivity to all four infrastructure services and the OpenAI API.
8. **Print summary** — Shows results and next steps.

Every step is idempotent — running the script again skips work that's already done.

---

## Running the Application

After setup completes:

```bash
python run.py
```

This starts the backend API (port 8000), Celery worker, and Next.js frontend (port 3000).

- **App UI:** http://localhost:3000
- **API docs:** http://localhost:8000/docs
- **Health check:** http://localhost:8000/health?check_services=true

Press `Ctrl+C` to stop all services.

To run without the Celery background worker (document ingestion won't work):
```bash
python run.py --no-celery
```

---

## Manual Setup

If you prefer to run each step yourself instead of using the script:

### 1. Start infrastructure

```bash
docker compose up -d
```

Wait for all containers to be healthy:
```bash
docker compose ps
```

### 2. Configure environment

```bash
cd backend
copy .env.example .env      # Windows
# cp .env.example .env      # Linux/macOS
```

Edit `backend/.env` and set `OPENAI_API_KEY` to your real key. All other defaults match docker-compose.

### 3. Create Python virtual environment

```bash
cd backend
python -m venv venv

# Windows:
.\venv\Scripts\activate

# Linux/macOS:
source venv/bin/activate

pip install -r requirements.txt
```

### 4. Run database setup

```bash
cd backend
python -m scripts.setup.setup_all
```

This runs Alembic migrations, creates Milvus collections, and creates MinIO buckets.

### 5. Install frontend dependencies

```bash
cd frontend
npm install
```

### 6. Verify connections

```bash
cd backend
python -m scripts.setup.verify_connections
```

### 7. Start the application

```bash
python run.py
```

---

## Configuration

All backend config is in `backend/.env` via Pydantic BaseSettings. The `.env.example` file documents every option.

### Required

| Variable | Description |
|----------|-------------|
| `OPENAI_API_KEY` | Your OpenAI API key (for embeddings) |

### Infrastructure (defaults match docker-compose)

| Variable | Default | Description |
|----------|---------|-------------|
| `DB_HOST` | localhost | PostgreSQL host |
| `DB_PORT` | 5432 | PostgreSQL port |
| `DB_NAME` | ragdb | Database name |
| `DB_USER` | raguser | Database user |
| `DB_PASSWORD` | ragpass | Database password |
| `MILVUS_HOST` | localhost | Milvus host |
| `MILVUS_PORT` | 19530 | Milvus port |
| `MINIO_ENDPOINT` | localhost:9000 | MinIO endpoint |
| `MINIO_ACCESS_KEY` | minioadmin | MinIO access key |
| `MINIO_SECRET_KEY` | minioadmin | MinIO secret key |
| `REDIS_URL` | redis://localhost:6379/0 | Celery broker |
| `REDIS_BACKEND` | redis://localhost:6379/1 | Celery result backend |

### Using Remote Infrastructure

If you have services running on a remote server, update `backend/.env`:

```bash
DB_HOST=192.168.1.100
MILVUS_HOST=192.168.1.100
MINIO_ENDPOINT=192.168.1.100:9000
REDIS_URL=redis://192.168.1.100:6379/0
```

Then pass `-SkipDocker` (Windows) or `--skip-docker` (Linux) to the setup script.

---

## Troubleshooting

### Port conflicts

If a port is already in use, either stop the conflicting process or change the port in `docker-compose.yml` and `backend/.env`.

**Windows — find what's using a port:**
```powershell
netstat -ano | findstr :5432
taskkill /PID <pid> /F
```

**Linux — find what's using a port:**
```bash
sudo lsof -i :5432
sudo kill <pid>
```

### Milvus is slow to start

Milvus depends on etcd and minio-milvus. It can take 60-90 seconds to become healthy on first start. The setup script waits up to 3 minutes. If it times out:

```bash
docker compose logs milvus
```

Common causes: not enough RAM (Milvus needs ~2GB), etcd didn't start cleanly (try `docker compose down && docker compose up -d`).

### Python venv issues on Windows

If `python` is not found, try `py -3` (the Windows Python Launcher). The setup script checks both.

If `pip install` fails with a build error, make sure you have the [Visual C++ Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/) installed.

### Missing OpenAI API key

If you see connection errors from the OpenAI check, make sure `OPENAI_API_KEY` in `backend/.env` is set to a valid key (starts with `sk-`). Get one at https://platform.openai.com/api-keys.

### Docker containers won't start

Make sure Docker Desktop is running. On Windows, check that WSL 2 is enabled. Run `docker compose logs` to see specific errors.

### Frontend build errors

If `npm install` fails, try deleting `frontend/node_modules` and `frontend/package-lock.json`, then run `npm install` again.

---

## Cleanup / Reset

**Stop infrastructure and delete all data (start fresh):**
```bash
docker compose down -v
```

**Remove Python virtual environment:**
```bash
rmdir /s /q backend\venv         # Windows
rm -rf backend/venv              # Linux/macOS
```

**Remove frontend dependencies:**
```bash
rmdir /s /q frontend\node_modules  # Windows
rm -rf frontend/node_modules       # Linux/macOS
```

**Remove backend config:**
```bash
del backend\.env          # Windows
rm backend/.env           # Linux/macOS
```

Then re-run the setup script to rebuild everything.

---

## Linux / macOS Note

`run.py` supports Linux/macOS and Windows. You can use `python run.py` directly.
If you prefer manual startup, use:

**Terminal 1 — Backend:**
```bash
cd backend
source venv/bin/activate
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

**Terminal 2 — Celery worker:**
```bash
cd backend
source venv/bin/activate
celery -A app.worker worker --loglevel=info --pool=prefork --concurrency=4
```
On Windows, use `--pool=solo`.

**Terminal 3 — Frontend:**
```bash
cd frontend
npm run dev
```

---

## First Document

Once everything is running:

1. Open http://localhost:3000
2. Click **Upload Document** in the sidebar
3. Select a PDF file
4. Wait for processing to complete
5. Go to **Chat** and ask questions about your document

Or via API:
```bash
curl -X POST http://localhost:8000/v1/ingest/document \
  -F "file=@/path/to/document.pdf"
```

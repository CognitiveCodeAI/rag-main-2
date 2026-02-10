# NPR - Near-Perfect RAG

A production-grade Retrieval-Augmented Generation (RAG) system designed for high-accuracy document question answering with evidence-based citations.

## Overview

NPR (Near-Perfect RAG) is a full-stack RAG system that retrieves relevant document evidence and generates answers with explicit citations. The system prioritizes:

- **Evidence-first answers**: Every claim is grounded in retrieved document evidence
- **Citation completeness**: All factual claims include source citations with page numbers
- **Explicit abstention**: When insufficient evidence exists, the system asks clarifying questions or abstains rather than guessing
- **Reproducibility**: Every response produces a replayable trace for debugging and auditing

## Architecture

```
                                    NPR RAG System
    ┌─────────────────────────────────────────────────────────────────────┐
    │                           ONLINE PLANE                               │
    │  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────────┐  │
    │  │  Query   │───▶│ Planner  │───▶│ Retrieve │───▶│   Generate   │  │
    │  │ Gateway  │    │          │    │ & Rerank │    │ (with cites) │  │
    │  └──────────┘    └──────────┘    └──────────┘    └──────────────┘  │
    └─────────────────────────────────────────────────────────────────────┘
                                        │
                    ┌───────────────────┼───────────────────┐
                    ▼                   ▼                   ▼
              ┌──────────┐       ┌──────────┐       ┌──────────┐
              │PostgreSQL│       │  Milvus  │       │  MinIO   │
              │ (Graph)  │       │ (Vectors)│       │ (Storage)│
              └──────────┘       └──────────┘       └──────────┘
    ┌─────────────────────────────────────────────────────────────────────┐
    │                          OFFLINE PLANE                               │
    │  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────────┐  │
    │  │  Ingest  │───▶│  Parse   │───▶│  Chunk   │───▶│    Embed     │  │
    │  │ Document │    │ & Layout │    │ & Index  │    │  (OpenAI)    │  │
    │  └──────────┘    └──────────┘    └──────────┘    └──────────────┘  │
    └─────────────────────────────────────────────────────────────────────┘
```

## Tech Stack

| Component | Technology |
|-----------|------------|
| Backend API | FastAPI (Python 3.11+) |
| Frontend | Next.js |
| Vector Database | Milvus |
| Relational DB | PostgreSQL |
| Object Storage | MinIO (S3-compatible) |
| Task Queue | Celery + Redis |
| Embeddings | OpenAI text-embedding-3-large |
| LLM (Chat) | Configurable (Ollama/OpenAI) |

## Quick Start

> **First time?** See [SETUP.md](SETUP.md) for comprehensive setup instructions with troubleshooting.

### Prerequisites

- Python 3.11+ (`python --version`)
- Node.js 18+ (`node --version`)
- Docker & Docker Compose (`docker --version`)
- OpenAI API key ([get one here](https://platform.openai.com/api-keys))

### 1. Clone and Start Infrastructure

```bash
git clone <repository-url> rag-system
cd rag-system

# Option A (recommended when you already have ai-* containers running):
# Reuse existing Docker services and skip starting duplicate infrastructure.
# Ensure postgres/redis/minio/milvus are already up on localhost ports.

# Option B (fresh local stack):
docker compose up -d
docker compose ps
```

Option B starts PostgreSQL, Milvus, MinIO, and Redis for this repo.
If ports `5432`, `6379`, `9000`, or `19530` are already in use, either reuse your
existing stack and point `backend/.env` to it, or remap ports in `docker-compose.yml`.

### 2. Configure Backend

```bash
cd backend

# Create virtual environment
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Linux/macOS

# Install dependencies
pip install -r requirements.txt

# Copy and configure environment
copy .env.example .env       # Windows
# cp .env.example .env       # Linux/macOS
```

**Important**: Edit `.env` and set your OpenAI API key:
```
OPENAI_API_KEY=sk-your-actual-key-here
```

If you are reusing existing Docker services, set connection fields in `.env`
(`DB_*`, `MILVUS_*`, `MINIO_*`, `REDIS_*`) to match those running containers.

### 3. Initialize Database

```bash
# Run setup script (from backend directory)
python -m scripts.setup.setup_all
```

### 4. Start Backend

```bash
# Start API server
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Verify it's running: http://localhost:8000/health

### 5. Start Frontend (Optional)

```bash
cd frontend
npm install
npm run dev
```

Access UI at: http://localhost:3000

### 6. Start Celery Worker (Optional - for background processing)

```bash
# In a new terminal, with venv activated
cd backend
celery -A app.worker worker --loglevel=info
```

## API Endpoints

Once running, access:

- **API Docs**: http://localhost:8000/docs (Swagger UI)
- **Health Check**: http://localhost:8000/health
- **Frontend**: http://localhost:3000

### Key Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/ingest/document` | POST | Upload and process documents |
| `/v1/qa/ask` | POST | Ask questions about documents |
| `/v1/retrieve/vector` | POST | Vector search for relevant chunks |
| `/api/query` | POST | Query endpoint (legacy) |
| `/health` | GET | System health status |

## Project Structure

```
rag/
├── backend/
│   ├── app/
│   │   ├── db/          # Database models & sessions
│   │   ├── graph/       # Document graph processing
│   │   ├── llm/         # LLM clients (OpenAI)
│   │   ├── qa/          # Question answering pipeline
│   │   ├── routes/      # FastAPI routes
│   │   ├── tasks/       # Celery background tasks
│   │   └── vectordb/    # Milvus vector operations
│   ├── scripts/         # Setup and utility scripts
│   ├── tests/           # Test suite
│   └── docs/            # Documentation
├── frontend/            # Next.js frontend
├── contracts/           # JSON schema contracts
├── docker-compose.yml   # Infrastructure setup
└── lighthouse.md        # System specification
```

## Documentation

- [Setup Guide](SETUP.md) - **Complete setup instructions with troubleshooting**
- [Quick Start Guide](backend/docs/QUICK_START.md) - Condensed setup steps
- [Deployment Guide](backend/docs/DEPLOYMENT_GUIDE.md) - Production deployment
- [System Specification](lighthouse.md) - Full architecture spec
- [Prompting Guide](PROMPTING_GUIDE.md) - Prompt engineering practices

## Configuration

See [backend/.env.example](backend/.env.example) for all configuration options.

Key settings:

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | Yes | OpenAI API key for embeddings |
| `DB_PASSWORD` | Yes | PostgreSQL password |
| `MINIO_SECRET_KEY` | Yes | MinIO secret key |
| `DEBUG` | No | Enable debug mode (default: true) |

## Testing

```bash
cd backend

# Run all tests
pytest

# Run specific test suite
pytest tests/qa/ -v

# Run with coverage
pytest --cov=app tests/
```

## Development

### Adding a New Document Type

1. Add parser in `backend/app/graph/`
2. Update chunking logic in `backend/app/graph/chunker.py`
3. Add tests in `backend/tests/`

### Running Evaluations

```bash
cd backend
python tests/eval/run_qa_eval.py
```

## License

[Add your license here]

## Contributing

[Add contribution guidelines]

# RAG Document Chat System - Deployment Guide

A comprehensive guide for deploying and configuring the RAG (Retrieval-Augmented Generation) document chat system from scratch.

---

## Table of Contents

1. [Quick Start (Existing Infrastructure)](#quick-start-existing-infrastructure)
2. [System Overview](#system-overview)
3. [Infrastructure Requirements](#infrastructure-requirements)
4. [Prerequisites](#prerequisites)
5. [Infrastructure Setup](#infrastructure-setup)
6. [Application Setup](#application-setup)
7. [Configuration](#configuration)
8. [Database Initialization](#database-initialization)
9. [Verification](#verification)
10. [Document Ingestion](#document-ingestion)
11. [Using the System](#using-the-system)
12. [Troubleshooting](#troubleshooting)

---

## Quick Start (Existing Infrastructure)

If your infrastructure (PostgreSQL, Milvus, MinIO, Redis) is already running, use this quick start guide.

### 1. Get the Application Code

```powershell
# Clone or copy the application to your server
git clone <repository-url> rag-system
cd rag-system
```

### 2. Configure Backend

```powershell
cd backend

# Create virtual environment
python -m venv venv

# Activate (Windows)
.\venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Create configuration from template
copy .env.example .env
```

Edit `.env` with your server details:

```env
# PostgreSQL
DB_HOST=your-postgres-host
DB_PORT=5432
DB_NAME=ragdb
DB_USER=raguser
DB_PASSWORD=your-password

# Milvus
MILVUS_HOST=your-milvus-host
MILVUS_PORT=19530

# MinIO
MINIO_ENDPOINT=your-minio-host:9000
MINIO_ACCESS_KEY=your-access-key
MINIO_SECRET_KEY=your-secret-key

# Redis
REDIS_URL=redis://your-redis-host:6379/0
REDIS_BACKEND=redis://your-redis-host:6379/1

# OpenAI (required for embeddings)
OPENAI_API_KEY=sk-your-api-key
```

### 3. Run Setup Scripts

The setup scripts will create all required databases, collections, and buckets:

```powershell
# Run all setup steps
python -m scripts.setup.setup_all
```

This script:
- Creates PostgreSQL tables via Alembic migrations
- Creates Milvus vector collections (graph_chunks_v2, graph_figures_v2, graph_tables_v2)
- Creates MinIO buckets (npr-corpus, npr-traces)
- Verifies all connections

To run individual steps:

```powershell
python -m scripts.setup.setup_postgres    # PostgreSQL only
python -m scripts.setup.setup_milvus      # Milvus only
python -m scripts.setup.setup_minio       # MinIO only
python -m scripts.setup.verify_connections # Verify all
```

### 4. Configure Frontend

```powershell
cd ..\frontend

# Install dependencies
npm install

# Create config
copy .env.example .env.local
```

Edit `frontend\.env.local`:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

### 5. Start the Application

**Backend:**

```powershell
cd backend
.\venv\Scripts\activate
uvicorn main:app --host 0.0.0.0 --port 8000
```

**Frontend:**

```powershell
cd frontend
npm run dev
```

### 6. Verify Installation

Open http://localhost:3000 in your browser.

Or test the API:

```powershell
curl http://localhost:8000/health
```

---

## System Overview

This system enables intelligent document chat by:
- Ingesting PDF documents into a graph-based knowledge structure
- Extracting text, figures, tables, and metadata
- Creating embeddings for semantic search
- Answering questions with citations from your documents

### Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Frontend      │────▶│   FastAPI       │────▶│   PostgreSQL    │
│   (Next.js)     │     │   Backend       │     │   (Metadata)    │
└─────────────────┘     └────────┬────────┘     └─────────────────┘
                                 │
                    ┌────────────┼────────────┐
                    ▼            ▼            ▼
            ┌───────────┐ ┌───────────┐ ┌───────────┐
            │  Milvus   │ │   MinIO   │ │  OpenAI   │
            │ (Vectors) │ │  (Files)  │ │   API     │
            └───────────┘ └───────────┘ └───────────┘
```

---

## Infrastructure Requirements

### Minimum Hardware

| Component | CPU | RAM | Storage |
|-----------|-----|-----|---------|
| Application Server | 4 cores | 8 GB | 50 GB SSD |
| PostgreSQL | 2 cores | 4 GB | 100 GB SSD |
| Milvus | 4 cores | 16 GB | 200 GB SSD |
| MinIO | 2 cores | 4 GB | 500 GB+ |

### Recommended Production

| Component | CPU | RAM | Storage |
|-----------|-----|-----|---------|
| Application Server | 8 cores | 16 GB | 100 GB SSD |
| PostgreSQL | 4 cores | 8 GB | 500 GB SSD |
| Milvus (Distributed) | 8 cores | 32 GB | 500 GB NVMe |
| MinIO | 4 cores | 8 GB | 2 TB+ |

---

## Prerequisites

### Required Software

| Software | Version | Purpose |
|----------|---------|---------|
| Python | 3.11+ | Backend runtime |
| Node.js | 18+ | Frontend runtime |
| PostgreSQL | 14+ | Relational database |
| Milvus | 2.3+ | Vector database |
| MinIO | Latest | Object storage |
| Redis | 7+ | Task queue (optional) |

### Required API Keys

| Service | Purpose | How to Obtain |
|---------|---------|---------------|
| OpenAI API | Embeddings & LLM | https://platform.openai.com/api-keys |

### Optional Services

| Service | Purpose |
|---------|---------|
| Ollama | Local OCR for scanned PDFs |

---

## Infrastructure Setup

### Option A: Docker Compose (Recommended for Development)

Create a `docker-compose.yml`:

```yaml
version: '3.8'

services:
  postgres:
    image: postgres:15
    environment:
      POSTGRES_USER: raguser
      POSTGRES_PASSWORD: ragpass
      POSTGRES_DB: ragdb
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data

  milvus:
    image: milvusdb/milvus:v2.3.16
    command: ["milvus", "run", "standalone"]
    environment:
      ETCD_ENDPOINTS: etcd:2379
      MINIO_ADDRESS: minio:9000
    ports:
      - "19530:19530"
      - "9091:9091"
    depends_on:
      - etcd
      - minio-milvus

  etcd:
    image: quay.io/coreos/etcd:v3.5.5
    environment:
      ETCD_AUTO_COMPACTION_MODE: revision
      ETCD_AUTO_COMPACTION_RETENTION: "1000"
      ETCD_QUOTA_BACKEND_BYTES: "4294967296"
    command: etcd -advertise-client-urls=http://127.0.0.1:2379 -listen-client-urls=http://0.0.0.0:2379

  minio-milvus:
    image: minio/minio:latest
    environment:
      MINIO_ACCESS_KEY: minioadmin
      MINIO_SECRET_KEY: minioadmin
    command: minio server /data
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9000/minio/health/live"]
      interval: 30s
      timeout: 20s
      retries: 3

  minio:
    image: minio/minio:latest
    environment:
      MINIO_ROOT_USER: minioadmin
      MINIO_ROOT_PASSWORD: minioadmin
    ports:
      - "9000:9000"
      - "9001:9001"
    command: server /data --console-address ":9001"
    volumes:
      - minio_data:/data

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

volumes:
  postgres_data:
  minio_data:
```

Start the infrastructure:

```bash
docker-compose up -d
```

### Option B: Standalone Services

#### PostgreSQL

```bash
# Ubuntu/Debian
sudo apt install postgresql postgresql-contrib
sudo -u postgres createuser -P raguser
sudo -u postgres createdb -O raguser ragdb

# Enable connections
sudo nano /etc/postgresql/15/main/pg_hba.conf
# Add: host ragdb raguser 0.0.0.0/0 md5
sudo systemctl restart postgresql
```

#### Milvus

Follow the official guide: https://milvus.io/docs/install_standalone-docker.md

```bash
# Download docker-compose
wget https://github.com/milvus-io/milvus/releases/download/v2.3.16/milvus-standalone-docker-compose.yml -O docker-compose.yml

# Start Milvus
docker-compose up -d
```

#### MinIO

```bash
docker run -d \
  -p 9000:9000 \
  -p 9001:9001 \
  --name minio \
  -e "MINIO_ROOT_USER=minioadmin" \
  -e "MINIO_ROOT_PASSWORD=minioadmin" \
  -v /data/minio:/data \
  minio/minio server /data --console-address ":9001"
```

---

## Application Setup

### 1. Clone the Repository

```bash
git clone <repository-url> rag-system
cd rag-system
```

### 2. Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv venv

# Activate (Windows)
.\venv\Scripts\activate

# Activate (Linux/Mac)
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Frontend Setup

```bash
cd frontend

# Install dependencies
npm install
```

---

## Configuration

### Backend Configuration

Create `backend/.env`:

```env
# ===========================================
# DATABASE CONFIGURATION
# ===========================================
DATABASE_URL=postgresql://raguser:ragpass@localhost:5432/ragdb

# ===========================================
# MILVUS CONFIGURATION
# ===========================================
MILVUS_HOST=localhost
MILVUS_PORT=19530

# ===========================================
# MINIO CONFIGURATION
# ===========================================
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET=rag-documents
MINIO_SECURE=false

# ===========================================
# OPENAI CONFIGURATION (REQUIRED)
# ===========================================
OPENAI_API_KEY=sk-your-openai-api-key-here

# ===========================================
# EMBEDDING CONFIGURATION
# ===========================================
EMBEDDING_MODEL=text-embedding-3-large
EMBEDDING_DIM=3072

# ===========================================
# LLM CONFIGURATION
# ===========================================
LLM_MODEL=gpt-4o
LLM_MAX_TOKENS=4096

# ===========================================
# OPTIONAL: OLLAMA OCR (for scanned PDFs)
# ===========================================
# OLLAMA_BASE_URL=http://localhost:11434
# OLLAMA_OCR_MODEL=llava

# ===========================================
# OPTIONAL: REDIS (for background tasks)
# ===========================================
# REDIS_URL=redis://localhost:6379/0
```

### Frontend Configuration

Create `frontend/.env.local`:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

---

## Database Initialization

> **Tip:** For automated setup, use the setup scripts instead:
> ```powershell
> python -m scripts.setup.setup_all
> ```
> This runs all the steps below automatically. See [Quick Start](#quick-start-existing-infrastructure) for details.

### 1. Run PostgreSQL Migrations

```bash
cd backend

# Activate virtual environment
.\venv\Scripts\activate  # Windows
source venv/bin/activate  # Linux/Mac

# Run Alembic migrations
alembic upgrade head
```

This creates the following tables:
- `documents_graph` - Document metadata
- `nodes` - Chunks, figures, tables
- `edges` - Relationships between nodes
- `content_registry` - Content deduplication

### 2. Initialize Milvus Collections

```bash
cd backend

python -c "
from app.graph.vector_index import GraphVectorIndex

# Create v2 collections with metadata fields
index = GraphVectorIndex(collection_version='v2')
index.ensure_collections()

# Verify
for node_type in ['chunk', 'figure', 'table']:
    stats = index.get_collection_stats(node_type)
    print(f'{node_type}: {stats}')
"
```

Expected output:
```
chunk: {'name': 'graph_chunks_v2', 'num_entities': 0, 'index_status': 'indexed', 'version': 'v2'}
figure: {'name': 'graph_figures_v2', 'num_entities': 0, 'index_status': 'indexed', 'version': 'v2'}
table: {'name': 'graph_tables_v2', 'num_entities': 0, 'index_status': 'indexed', 'version': 'v2'}
```

### 3. Initialize MinIO Buckets

```bash
cd backend

python -c "
from minio import Minio
import os

client = Minio(
    os.getenv('MINIO_ENDPOINT', 'localhost:9000'),
    access_key=os.getenv('MINIO_ACCESS_KEY', 'minioadmin'),
    secret_key=os.getenv('MINIO_SECRET_KEY', 'minioadmin'),
    secure=False
)

bucket = os.getenv('MINIO_BUCKET', 'rag-documents')
if not client.bucket_exists(bucket):
    client.make_bucket(bucket)
    print(f'Created bucket: {bucket}')
else:
    print(f'Bucket exists: {bucket}')
"
```

---

## Verification

### Test All Connections

```bash
cd backend

python -c "
print('Testing connections...')

# 1. PostgreSQL
from app.db.session import get_session
db = next(get_session())
print('✓ PostgreSQL connected')
db.close()

# 2. Milvus
from pymilvus import connections, utility
from app.config import get_settings
settings = get_settings()
connections.connect('default', host=settings.milvus_host, port=settings.milvus_port)
print(f'✓ Milvus connected (v{utility.get_server_version()})')

# 3. OpenAI
from app.embeddings.client import EmbeddingClient
client = EmbeddingClient()
emb, tokens = client.embed_single('test')
print(f'✓ OpenAI connected (dim={len(emb)})')

print()
print('All systems ready!')
"
```

---

## Document Ingestion

### Method 1: Python Script

```python
from pathlib import Path
from app.db.session import get_session
from app.graph.pipeline import GraphIngestionPipeline
from app.tasks.embed_nodes import embed_document_nodes_sync

# Initialize
db = next(get_session())
pipeline = GraphIngestionPipeline(db, skip_ocr=True)

# Ingest a PDF
pdf_path = Path("path/to/document.pdf")
pdf_bytes = pdf_path.read_bytes()

result = pipeline.ingest(
    pdf_bytes=pdf_bytes,
    source_uri=f"file://{pdf_path}"
)

print(f"Ingested: {result.doc_id}")
print(f"  Pages: {result.total_pages}")
print(f"  Chunks: {result.total_chunks}")
print(f"  Figures: {result.total_figures}")

# Generate embeddings
embed_result = embed_document_nodes_sync(
    doc_id=result.doc_id,
    version=result.version,
    db=db
)

print(f"  Embedded: {embed_result['embedded']}")
print(f"  Indexed: {embed_result['indexed']}")

db.close()
```

### Method 2: API Endpoint

Start the backend server:

```bash
cd backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Upload via API:

```bash
curl -X POST "http://localhost:8000/v1/ingest/document" ^
  -F "file=@document.pdf"

# Linux/Mac:
curl -X POST "http://localhost:8000/v1/ingest/document" \
  -F "file=@document.pdf"
```

### Method 3: Batch Ingestion

```python
from pathlib import Path
from app.db.session import get_session
from app.graph.pipeline import GraphIngestionPipeline
from app.tasks.embed_nodes import embed_document_nodes_sync

db = next(get_session())
pipeline = GraphIngestionPipeline(db, skip_ocr=True)

# Ingest all PDFs in a directory
pdf_dir = Path("path/to/documents")
for pdf_path in pdf_dir.glob("*.pdf"):
    print(f"Processing: {pdf_path.name}")
    
    result = pipeline.ingest(
        pdf_bytes=pdf_path.read_bytes(),
        source_uri=f"file://{pdf_path}"
    )
    
    if not result.is_content_duplicate:
        embed_document_nodes_sync(result.doc_id, result.version, db)
        print(f"  ✓ Ingested and embedded")
    else:
        print(f"  → Duplicate (canonical: {result.canonical_doc_id})")

db.close()
```

---

## Using the System

### Start the Backend

```bash
cd backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Start the Frontend

```bash
cd frontend
npm run dev
```

### Ask Questions via API

```bash
curl -X POST "http://localhost:8000/v1/qa/ask" ^
  -H "Content-Type: application/json" ^
  -d "{\"doc_id\": \"YOUR_DOC_ID\", \"question\": \"What is the main conclusion of this document?\"}"
```

Or on Linux/Mac:

```bash
curl -X POST "http://localhost:8000/v1/qa/ask" \
  -H "Content-Type: application/json" \
  -d '{
    "doc_id": "YOUR_DOC_ID",
    "question": "What is the main conclusion of this document?"
  }'
```

### Response Format

```json
{
  "question": "What is the main conclusion?",
  "answer": "The main conclusion is...",
  "citations": [
    {
      "node_id": "abc123",
      "page_no": 15,
      "text": "Quoted text from document..."
    }
  ],
  "success": true
}
```

---

## Troubleshooting

### Common Issues

#### PostgreSQL Connection Failed

```
Error: connection refused
```

**Solution:**
- Verify PostgreSQL is running: `sudo systemctl status postgresql`
- Check connection string in `.env`
- Ensure user has permissions: `GRANT ALL ON DATABASE ragdb TO raguser;`

#### Milvus Flush Fails

```
MilvusException: channel not found
```

**Solution:**
- Restart Milvus: `docker restart milvus-standalone`
- Drop and recreate collections if persistent

#### OpenAI API Error

```
Error: Invalid API Key
```

**Solution:**
- Verify `OPENAI_API_KEY` in `.env`
- Check API key at https://platform.openai.com/api-keys
- Ensure billing is set up

#### Out of Memory During Embedding

**Solution:**
- Process documents in smaller batches
- Increase server RAM
- Use a smaller embedding model

### Health Check Script

```bash
cd backend
python -c "
from app.db.session import get_session
from app.db.graph_models import DocumentGraph, Node
from pymilvus import connections, utility
from app.config import get_settings

db = next(get_session())
settings = get_settings()

# Database stats
doc_count = db.query(DocumentGraph).count()
node_count = db.query(Node).count()
print(f'PostgreSQL: {doc_count} documents, {node_count} nodes')

# Milvus stats
connections.connect('default', host=settings.milvus_host, port=settings.milvus_port)
from app.graph.vector_index import GraphVectorIndex
idx = GraphVectorIndex()
for t in ['chunk', 'figure', 'table']:
    stats = idx.get_collection_stats(t)
    print(f'Milvus {t}: {stats[\"num_entities\"]} vectors')

db.close()
"
```

---

## Security Considerations

### Production Checklist

- [ ] Change all default passwords
- [ ] Enable TLS/SSL for all services
- [ ] Configure firewall rules
- [ ] Set up API authentication
- [ ] Enable database backups
- [ ] Configure rate limiting
- [ ] Set up monitoring/alerting

### Environment Variables (Production)

Never commit `.env` files. Use environment variables or secrets management:

```bash
# Example: Using environment variables
export DATABASE_URL="postgresql://user:pass@host:5432/db"
export OPENAI_API_KEY="sk-..."
```

---

## Support

For issues:
1. Check the troubleshooting section
2. Review logs: `tail -f backend/logs/app.log`
3. Open an issue with:
   - Error message
   - Steps to reproduce
   - Environment details

---

*Last updated: January 2026*

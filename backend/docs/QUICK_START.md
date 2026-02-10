# Quick Start Guide

Get the RAG Document Chat System running in 10 minutes.

---

## Prerequisites

You need:
- Python 3.11+
- Docker & Docker Compose
- OpenAI API key

---

## 1. Start Infrastructure (2 min)

```bash
# Clone the repo
git clone <repository-url> rag-system
cd rag-system

# Start databases with Docker
docker-compose up -d
```

This starts:
- PostgreSQL (port 5432)
- Milvus (port 19530)
- MinIO (port 9000)
- Redis (port 6379)

---

## 2. Configure Backend (1 min)

```powershell
cd backend

# Copy environment template
copy .env.example .env    # Windows
# cp .env.example .env    # Linux/Mac

# Edit .env and set your OpenAI API key
# Required: OPENAI_API_KEY=sk-your-actual-key
```

**Important:** Edit `.env` and replace `your-openai-api-key-here` with your actual OpenAI API key.

---

## 3. Setup Backend (3 min)

```bash
# Create virtual environment
python -m venv venv

# Activate (Windows)
.\venv\Scripts\activate

# Activate (Linux/Mac)
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run database migrations
alembic upgrade head

# Initialize Milvus collections
python -c "
from app.graph.vector_index import GraphVectorIndex
idx = GraphVectorIndex(collection_version='v2')
idx.ensure_collections()
print('Milvus ready!')
"
```

---

## 4. Ingest Your First Document (2 min)

```bash
# Place a PDF in the current directory, then run:
python -c "
from pathlib import Path
from app.db.session import get_session
from app.graph.pipeline import GraphIngestionPipeline
from app.tasks.embed_nodes import embed_document_nodes_sync

# Find first PDF in current directory
pdf = next(Path('.').glob('*.pdf'), None)
if not pdf:
    print('No PDF found. Place a PDF in the current directory.')
    exit(1)

print(f'Ingesting: {pdf.name}')

db = next(get_session())
pipeline = GraphIngestionPipeline(db, skip_ocr=True)

result = pipeline.ingest(
    pdf_bytes=pdf.read_bytes(),
    source_uri=f'file://{pdf.absolute()}'
)

print(f'  doc_id: {result.doc_id}')
print(f'  pages: {result.total_pages}')
print(f'  chunks: {result.total_chunks}')

print('Generating embeddings...')
embed_result = embed_document_nodes_sync(result.doc_id, result.version, db)
print(f'  embedded: {sum(embed_result[\"embedded\"].values())} nodes')

db.close()
print('Done!')
"
```

---

## 5. Ask a Question (1 min)

```bash
# Replace DOC_ID with the doc_id from step 4
python -c "
from app.db.session import get_session
from app.qa.runner import QARunner

db = next(get_session())
runner = QARunner(db)

# Get the most recent document
from app.db.graph_models import DocumentGraph
doc = db.query(DocumentGraph).order_by(DocumentGraph.ingested_at.desc()).first()

if not doc:
    print('No documents found. Run step 4 first.')
    exit(1)

print(f'Document: {doc.doc_id}')
print()

question = 'What is this document about?'
print(f'Q: {question}')

result = runner.run(doc.doc_id, question)

print(f'A: {result.answer}')
print()
print('Citations:')
for c in result.citations[:3]:
    print(f'  - Page {c.page_no}: {c.text[:100]}...')

db.close()
"
```

---

## 6. Start the API Server

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

API is now available at `http://localhost:8000`

### Test the API

```powershell
# Check health
curl http://localhost:8000/health

# Ask a question (replace YOUR_DOC_ID with the doc_id from step 4)
# Windows:
curl -X POST http://localhost:8000/v1/qa/ask -H "Content-Type: application/json" -d "{\"doc_id\": \"YOUR_DOC_ID\", \"question\": \"What is this about?\"}"

# Linux/Mac:
curl -X POST http://localhost:8000/v1/qa/ask \
  -H "Content-Type: application/json" \
  -d '{"doc_id": "YOUR_DOC_ID", "question": "What is this about?"}'
```

---

## Next Steps

- Read the full [Deployment Guide](DEPLOYMENT_GUIDE.md)
- Set up the frontend: `cd frontend && npm install && npm run dev`
- Ingest more documents
- Configure OCR for scanned PDFs

---

## Troubleshooting

**"Connection refused" errors:**
```bash
# Check if Docker containers are running
docker ps
```

**"Invalid API key" errors:**
- Verify your OpenAI API key in `.env`

**"No module named 'app'":**
```bash
# Make sure you're in the backend directory with venv activated
cd backend
.\venv\Scripts\activate  # Windows
source venv/bin/activate  # Linux/Mac
```

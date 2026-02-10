# NPR Operations Runbook

Lessons learned and troubleshooting procedures from the Feb 2026 QA evaluation effort. This document covers infrastructure recovery, common pitfalls, and operational procedures.

---

## Table of Contents

1. [Infrastructure Overview](#1-infrastructure-overview)
2. [Milvus Recovery After Power Failure](#2-milvus-recovery-after-power-failure)
3. [Milvus Data Loss and Re-ingestion](#3-milvus-data-loss-and-re-ingestion)
4. [Document ID Mismatch Between Systems](#4-document-id-mismatch-between-systems)
5. [Celery Worker Troubleshooting](#5-celery-worker-troubleshooting)
6. [Running the QA Eval Script](#6-running-the-qa-eval-script)
7. [PostgreSQL Connection Issues](#7-postgresql-connection-issues)
8. [Ubuntu Server Access](#8-ubuntu-server-access)
9. [Windows Development Environment Gotchas](#9-windows-development-environment-gotchas)

---

## 1. Infrastructure Overview

The application uses a split infrastructure model:

| Service    | Location                       | Notes                                      |
|------------|--------------------------------|--------------------------------------------|
| PostgreSQL | localhost:5432 (Docker)        | Container: `rag-postgres`                  |
| Redis      | localhost:6379 (Docker)        | Container: `rag-redis`                     |
| MinIO      | localhost:9000 (Docker)        | Container: `rag-minio`                     |
| Milvus     | 192.168.100.25:19530 (remote)  | Standalone systemd service (NOT Docker)    |
| Backend    | localhost:8000                 | FastAPI + Celery worker                    |
| Frontend   | localhost:3000                 | Next.js                                    |

**Key point**: Milvus runs on a remote Ubuntu server as a standalone binary, while all other services run locally in Docker. This split means Milvus has different failure modes and recovery procedures than the local Docker services.

### Milvus Server Layout (192.168.100.25)

```
/usr/bin/milvus                          # Binary
/etc/milvus/configs/milvus.yaml          # Main config (storageType: local)
/etc/milvus/configs/embedEtcd.yaml       # Embedded etcd config
/var/lib/milvus/data/                    # Vector data (insert_log, index_files)
/var/lib/milvus/rdb_data/                # RocksMQ message queue data
/var/lib/milvus/rdb_data_meta_kv/        # RocksMQ metadata
/default.etcd/                           # Embedded etcd data (on root filesystem!)
```

**Warning**: The embedded etcd stores its data at `/default.etcd/` on the root filesystem because no `data.dir` is configured in `embedEtcd.yaml`. This is non-obvious and can be missed during backups.

---

## 2. Milvus Recovery After Power Failure

### Symptoms

- `collection.load()` hangs indefinitely or times out
- Milvus logs show: `"find no available rootcoord"`
- Querycoord task scheduler stuck in infinite `channel subscribe` loop with `committedNum=0`
- Checkpoint timestamps are hours/days stale

### Root Cause

Power failure corrupts RocksMQ (the embedded RocksDB-based message queue). Milvus components (rootcoord, querycoord, datacoord) communicate via RocksMQ, and corrupted queue state prevents them from coordinating.

### Fix Procedure

```bash
# SSH to Ubuntu server
ssh bizon@192.168.100.25

# 1. Stop Milvus
echo 'root' | sudo -S systemctl stop milvus

# 2. Back up (don't delete) the corrupted RocksMQ data
echo 'root' | sudo -S mv /var/lib/milvus/rdb_data /var/lib/milvus/rdb_data.bak.$(date +%Y%m%d)
echo 'root' | sudo -S mv /var/lib/milvus/rdb_data_meta_kv /var/lib/milvus/rdb_data_meta_kv.bak.$(date +%Y%m%d)

# 3. Restart Milvus
echo 'root' | sudo -S systemctl start milvus

# 4. Wait 30-60 seconds for transient errors to resolve
#    You will see "node not match" errors in logs — these are normal and self-resolve
sleep 60

# 5. Verify
echo 'root' | sudo -S systemctl status milvus
```

### What This Preserves vs. Loses

- **Preserved**: All flushed vector data (in `/var/lib/milvus/data/insert_log/` and `index_files/`), collection schemas, indexes
- **Lost**: Any data in unflushed segments (vectors inserted but not yet flushed to disk)

### Post-Recovery Verification

```python
from pymilvus import connections, utility, Collection

connections.connect(host="192.168.100.25", port="19530")
print(utility.list_collections())  # Should list collections

c = Collection("graph_chunks_v2")
c.load()
print(c.num_entities)  # Compare against expected count
```

### Transient Error: Node ID Mismatch

After restart you may see errors like:
```
node not match [expectedNodeID=27] [actualNodeID=28]
```

This happens because etcd still has the old node ID registered but the new Milvus instance gets a new ID. It resolves automatically in ~30 seconds as the old session expires.

**Do NOT panic and restart again** — just wait.

---

## 3. Milvus Data Loss and Re-ingestion

### Problem

After RocksMQ cleanup, entity counts may drop (e.g., 1747 -> 875). Unflushed segments are lost.

### How to Check What's Missing

```python
# Compare vectors in Milvus against graph nodes in PostgreSQL
from pymilvus import Collection, connections
connections.connect(host="192.168.100.25", port="19530")
c = Collection("graph_chunks_v2")
c.load()

# Get all doc_ids in Milvus
results = c.query(expr='doc_id != ""', output_fields=["doc_id"], limit=16384)
milvus_doc_ids = set(r["doc_id"] for r in results)
print(f"Doc IDs in Milvus: {milvus_doc_ids}")
print(f"Total entities: {c.num_entities}")
```

Then compare against PostgreSQL:
```sql
SELECT doc_id, COUNT(*) FROM nodes GROUP BY doc_id;
```

### Re-ingestion

The pipeline is idempotent — re-uploading a document with the same content will be detected via content hash and skipped. To force re-ingestion:

1. Delete the existing graph data (document_graph, nodes, edges) for that doc_id from PostgreSQL
2. Delete vectors for that doc_id from Milvus
3. Re-upload via the API

For simple re-embedding of existing chunks (when graph data is intact but vectors are missing), you may need a dedicated re-embed endpoint or script.

---

## 4. Document ID Mismatch Between Systems

### The Problem

This was the most time-consuming issue. The `doc_id` is a SHA256 hash of the `source_uri`, and the URI scheme matters:

| Upload method        | source_uri format           | doc_id (SHA256[:32])             |
|---------------------|-----------------------------|----------------------------------|
| API upload           | `upload://2025 FDD.pdf`     | `eea5a7954ff397d8db1cafc9aeb19f21` |
| Eval script (old)    | `file://C:/Apps/rag/2025 FDD.pdf` | `37660ee55b1fb2aa63579e3aeb2aca97` |

The eval script was computing its own `doc_id` using a `file://` URI, but the document was ingested via the API which uses an `upload://` URI. These produce completely different hashes.

### The Fix

The golden questions JSON now includes the correct `doc_id` directly:
```json
{
  "doc_id": "eea5a7954ff397d8db1cafc9aeb19f21",
  "pdf_path": "C:/Apps/rag/2025 FDD.pdf",
  "questions": [...]
}
```

And `run_qa_eval.py` uses it when available:
```python
doc_id = golden.get("doc_id")
if not doc_id:
    source_uri = f"file://{Path(pdf_path).resolve()}"
    doc_id = compute_doc_id(source_uri)
```

### How to Find a Document's Actual doc_id

```sql
-- From the graph tables (used by QA pipeline)
SELECT doc_id, filename, total_pages FROM documents_graph;

-- From the documents table (used by ingest tracking)
SELECT id, filename, doc_id FROM documents;
```

Or via Milvus:
```python
c = Collection("graph_chunks_v2")
c.load()
results = c.query(expr='doc_id != ""', output_fields=["doc_id"], limit=16384)
set(r["doc_id"] for r in results)
```

### Prevention

Always specify `doc_id` in golden question JSON files. Never rely on the eval script to recompute it unless you're certain the URI scheme matches what was used during ingestion.

---

## 5. Celery Worker Troubleshooting

### Symptoms

- Documents uploaded via API but never processed
- `IngestJob` status stays at `queued` indefinitely
- Redis queue has messages backing up

### Diagnosis

```bash
# Check if worker is running
tasklist | findstr celery

# Check Redis queue depth
python -c "import redis; r = redis.Redis(); print(r.llen('celery'))"
```

### Common Issue: Zombie Worker

The Celery worker process may be running (appears in task manager) but not consuming messages. This happens after crashes, power failures, or IDE restarts.

**Fix:**
```bash
# Kill the old worker
taskkill /F /IM celery.exe

# Start a new one (--pool=solo is REQUIRED on Windows)
cd backend
celery -A app.worker worker --loglevel=info --pool=solo
```

**Important**: On Windows, `--pool=solo` is required. Without it, the worker will fail silently or hang.

### Alternative: Use run.py

```bash
python run.py              # Starts backend + Celery + frontend
python run.py --no-celery  # Without Celery (for manual control)
```

---

## 6. Running the QA Eval Script

### Prerequisites

1. **Backend services running**: PostgreSQL, Milvus, Redis, MinIO must all be accessible
2. **OpenAI API key**: Required for embeddings — must be in environment or `.env`
3. **Document already ingested**: The eval script queries existing data; it doesn't ingest

### Running the Eval

The eval script needs the `.env` file loaded since it's not running through the FastAPI app:

```bash
cd backend
python -m tests.eval.run_qa_eval --golden tests/eval/golden_questions_fdd.json
```

If that doesn't pick up `.env`, use a wrapper:

```python
"""run_eval.py - Wrapper that loads .env before running eval."""
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path("C:/Apps/rag/backend/.env"))
sys.path.insert(0, "C:/Apps/rag/backend")

from tests.eval.run_qa_eval import main
sys.argv = [
    "run_qa_eval.py",
    "--golden", "C:/Apps/rag/backend/tests/eval/golden_questions_fdd.json",
]
main()
```

### Common Failure: "OpenAI API key not configured"

The eval script creates its own database session and settings, bypassing FastAPI's startup. If `OPENAI_API_KEY` isn't in the environment, embeddings will fail.

**Fix**: Ensure `load_dotenv()` runs before any app imports, or set the env var manually:
```bash
set OPENAI_API_KEY=sk-...
```

### Golden Questions JSON Format

```json
{
  "description": "Human-readable description",
  "pdf_path": "C:/Apps/rag/2025 FDD.pdf",
  "doc_id": "eea5a7954ff397d8db1cafc9aeb19f21",  // MUST match ingested doc_id
  "questions": [
    {
      "id": "q1",
      "question": "What is the initial franchise fee?",
      "category": "initial_fees",
      "expected_evidence": [{"page_no": 14, "node_type": "chunk"}],
      "expected_keywords": ["$45,000", "initial", "franchise fee"],
      "expected_answer_contains": "45,000"
    }
  ]
}
```

**Critical**: The `doc_id` field must match the actual document ID in the system. See [Section 4](#4-document-id-mismatch-between-systems) for how to find it.

---

## 7. PostgreSQL Connection Issues

### Password with Special Characters

The database password (`!1Shot@OneKill!`) contains `@` and `!` which break SQLAlchemy URL parsing.

**Wrong:**
```python
url = f"postgresql://user:!1Shot@OneKill!@host:5432/db"  # @ in password breaks parsing
```

**Correct:**
```python
from urllib.parse import quote_plus
password = quote_plus("!1Shot@OneKill!")
url = f"postgresql://user:{password}@host:5432/db"
```

The app's `config.py` handles this via Pydantic settings, but ad-hoc scripts connecting directly need to URL-encode the password.

---

## 8. Ubuntu Server Access

### SSH

Key-based auth is broken on the server. Use password auth:

```python
import paramiko
client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect("192.168.100.25", username="bizon", password="root")

stdin, stdout, stderr = client.exec_command("echo 'root' | sudo -S systemctl status milvus")
print(stdout.read().decode())
```

### sudo

All privileged commands require `echo 'root' | sudo -S` because the server expects password via stdin for sudo.

---

## 9. Windows Development Environment Gotchas

### Path Separators

- Python `Path` objects handle both `/` and `\` on Windows
- Shell commands (Git Bash, PowerShell) may choke on raw backslashes
- Use forward slashes in Python code: `"C:/Apps/rag/backend"`

### Celery on Windows

- **Must use** `--pool=solo` (prefork pool doesn't work on Windows)
- Worker may become zombie after crash — always check `tasklist` before starting a new one

### Python Module Imports

When running scripts from outside the backend directory, always add to `sys.path`:
```python
import sys
sys.path.insert(0, "C:/Apps/rag/backend")
```

And load `.env` before importing app modules:
```python
from dotenv import load_dotenv
load_dotenv("C:/Apps/rag/backend/.env")
# NOW import app modules
from app.config import get_settings
```

---

## Quick Reference: Common Commands

```bash
# Start everything
python run.py

# Start infrastructure
docker-compose up -d

# Check Milvus (remote)
python -c "from pymilvus import connections, utility; connections.connect(host='192.168.100.25', port='19530'); print(utility.list_collections())"

# Check Redis queue
python -c "import redis; r = redis.Redis(); print('Queue depth:', r.llen('celery'))"

# Check PostgreSQL
python -c "
from urllib.parse import quote_plus
from sqlalchemy import create_engine, text
e = create_engine(f'postgresql://raguser:{quote_plus(\"ragpass\")}@localhost:5432/ragdb')
with e.connect() as c:
    print(c.execute(text('SELECT COUNT(*) FROM nodes')).scalar(), 'nodes')
"

# Run QA eval
cd backend && python -m tests.eval.run_qa_eval --golden tests/eval/golden_questions_fdd.json

# Kill stuck Celery worker (Windows)
taskkill /F /IM celery.exe
```

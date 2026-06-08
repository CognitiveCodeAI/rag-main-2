# DISCOVERY.md

> Read-only discovery for NPR-RAG. No code was changed. Confidence tags: `[VERIFIED]` = observed in a tool call · `[INFERRED]` = strong single-source evidence · `[ASSUMED]` = best guess, no direct evidence. Do not promote tags until executed during repair.

## Repository shape
- Type: Single product, **multi-service repo** — not a package-manager monorepo (no workspaces/turbo/nx). Three top-level units: `backend/`, `frontend/`, `contracts/`. `[VERIFIED]`
- Languages: Python (backend), TypeScript/React (frontend), shared JSON-schema contracts. `[VERIFIED]`
- Frameworks/runtimes:
  - Backend: FastAPI `0.115.6`, SQLAlchemy `2.0.36`, Alembic `1.14.0`, Celery `5.4.0`, pymilvus `2.4.9`, openai `2.15.0`. `[VERIFIED]`
  - Frontend: Next.js `16.1.1`, React `19.2.3`, Vitest, ESLint. `[VERIFIED]`
  - Shared: `@npr/contracts` (local schema/types package; has `python/` + `schemas/`). Not imported directly by `frontend/src` or `backend/app` — appears to be a codegen/source-of-truth package. `[INFERRED]`
- Workspace in scope: **TBD — needs ratification** (full-stack local bring-up vs backend-only). See Open Questions.

## Intended behavior (inferred)
NPR ("Near-Perfect RAG") is a production-grade Retrieval-Augmented Generation system for document Q&A with evidence-based, page-level citations. Documents are parsed → split into page-bounded chunks → modeled as graph nodes/edges → embedded (OpenAI `text-embedding-3-large`) → stored across PostgreSQL (metadata/graph), Milvus (vectors), and MinIO (blobs). QA flow: question → embed → Milvus search → graph expansion → context packing → OpenAI GPT answer with citations and conflict detection. Optional multi-tenant ACL gates retrieval. Evidence: `README.md`, `CLAUDE.md`, `backend/app/qa/runner.py`, `backend/app/graph/pipeline.py`, `backend/app/acl/`. `[VERIFIED]`

## Setup commands
Preferred path is the `./dev` Bash CLI (wraps Docker, env, migrations, services). `[VERIFIED]` (script read)
- Bootstrap env: `./dev init` (creates/syncs `backend/.env` from `backend/.env.example`) `[VERIFIED]`
- Backend install: `cd backend && python -m venv venv && source venv/bin/activate && pip install -r requirements.txt` `[VERIFIED]` (how_to_run.txt)
- Frontend install: `cd frontend && npm install` `[VERIFIED]`
- Infra up: `docker compose up -d` (6 services) or `./dev up` `[VERIFIED]`
- DB init/migrate: `./dev migrate` (Alembic) or `python -m scripts.setup.setup_all` `[VERIFIED]`
- Build (frontend): `npm run build` `[VERIFIED]`
- Test (backend): `./dev test` or `cd backend && pytest` `[VERIFIED]`
- Test (frontend): `npm test` (`vitest run`) `[VERIFIED]`
- Lint (frontend): `npm run lint` (eslint) `[VERIFIED]`
- Typecheck (backend): no configured mypy/ruff found in root scan `[INFERRED]`
- Start everything: `./dev up`, or `python run.py`, or manual 3-terminal (uvicorn + celery + next). `[VERIFIED]`

## Required environment
- `OPENAI_API_KEY` — embeddings (`text-embedding-3-large`), QA generation (`gpt-5.2`), default OCR (`gpt-5-mini`). App **warns but does not crash** if unset (`main.py:42`); RAG operations fail at runtime without it. `[VERIFIED]`
- `DB_HOST/DB_PORT/DB_NAME/DB_USER/DB_PASSWORD` (defaults match compose: `raguser/ragpass@localhost:5432/ragdb`). `[VERIFIED]`
- `MILVUS_HOST/MILVUS_PORT` (default `localhost:19530`). `[VERIFIED]`
- `MINIO_ENDPOINT/MINIO_ACCESS_KEY/MINIO_SECRET_KEY` (default `localhost:9000` / `minioadmin`). `[VERIFIED]`
- `REDIS_URL` / `REDIS_BACKEND` (default `redis://localhost:6379/0` and `/1`). `[VERIFIED]`
- Optional: `ACL_ENABLED` (default false), `OCR_PROVIDER` (`openai`|`ollama`), `LLM_BASE_URL`/`LLM_MODEL` (Ollama, currently unused by QA path), `DOCLING_ENABLED_DEFAULT`. `[VERIFIED]`
- Frontend: `NEXT_PUBLIC_API_URL` (default `http://localhost:8000`). `[VERIFIED]`

## Blockers preventing local startup
1. **Docker infra footprint** — needs 6 running containers: `postgres:15-alpine`, `etcd v3.5.5`, `minio-milvus`, `milvus v2.3.16`, `minio`, `redis:7`. No Docker = no PostgreSQL/Milvus/MinIO/Redis. `[VERIFIED]` — severity: critical
2. **`OPENAI_API_KEY` absent / model access** — without a valid key the ingest and QA paths fail at runtime (startup still succeeds). Code targets `gpt-5.2` and `gpt-5-mini`; if those model IDs aren't enabled on the account, QA/OCR fail even with a valid key. `[VERIFIED]` (key) / `[INFERRED]` (model availability) — severity: high
3. **Node version vs Next.js 16** — `how_to_run.txt` says "Node 18+", but Next.js 16 requires Node **≥ 20.9**. On Node 18 the frontend dev/build is expected to fail. `[INFERRED]` — severity: high
4. **Python dep install friction** — `requirements.txt` carries a marshmallow/pymilvus compatibility note; pinned heavy deps (pymilvus, docling optional). Install may need Python 3.11+ exactly. `[INFERRED]` — severity: medium
5. **Migrations must run before use** — fresh PostgreSQL has no schema until `./dev migrate` / `setup_all`. `[VERIFIED]` — severity: medium
6. **Milvus server/client version skew** — server `v2.3.16` (compose) vs client `pymilvus 2.4.9`. Usually compatible but worth verifying on first connect. `[VERIFIED]` (versions) / `[ASSUMED]` (compat) — severity: low
7. **Repo path contains a leading space** (`/Users/larrystewart/Documents/ NPR-RAG`). Can break unquoted paths in scripts/tooling. `[VERIFIED]` — severity: low

## Proposed Mechanical Definition of Done
The repair phase is done when ALL of these check:
- [ ] `cd backend && pip install -r requirements.txt` exits 0 (Python 3.11+ venv)
- [ ] `cd frontend && npm install` exits 0 (Node ≥ 20.9)
- [ ] `docker compose up -d` brings all 6 services to healthy; `GET http://localhost:8000/health?check_services=true` reports PostgreSQL + Milvus + MinIO + Redis all connected
- [ ] `./dev migrate` (Alembic) exits 0 against the running PostgreSQL
- [ ] `cd frontend && npm run build` exits 0
- [ ] Backend starts (`uvicorn`/`./dev up`) and runs 30s without unhandled exception; frontend serves `http://localhost:3000`
- [ ] Backend test subset passes: pure unit tests green; infra-coupled connection tests pass only with infra up (specify accepted subset at ratification)
- [ ] **E2E smoke** `requires: valid OPENAI_API_KEY + enabled gpt-5.2/gpt-5-mini models` — ingest one small document via `POST /v1/ingest/document`, then `POST /v1/qa/ask` returns an answer with ≥1 citation. If the key or model access can't be supplied, this item is **deferred-with-reason**, not faked.
- [ ] Each blocker above has status: fixed | mitigated | deferred-with-reason

## Out of scope
- Production deployment (`backend/docs/DEPLOYMENT_GUIDE.md`), container image publishing, CI.
- The `contracts/` codegen pipeline (generating types/schemas) unless a build break surfaces it.
- ACL configuration/verification beyond confirming the default (disabled) path starts.
- Frontend end-to-end/UI testing beyond build + dev-server serve.
- Ollama-based local LLM/OCR path (default is OpenAI).
- Any code changes — this is observation only.

## Open questions for ratification
1. **Scope:** full local bring-up (infra + backend + frontend) or backend-only? This sets the DoD subset.
2. **Infra strategy:** stand up this repo's own `docker compose`, or reuse pre-existing shared `ai-*` Docker services that `how_to_run.txt` mentions?
3. **OpenAI access:** is a valid `OPENAI_API_KEY` available, and are `gpt-5.2` / `gpt-5-mini` enabled on that account? The E2E smoke check depends on it; if not, we deferr that DoD item.
4. **Local toolchain versions:** confirm Node ≥ 20.9 and Python 3.11+ are available (drives blockers #3/#4).
5. **Acceptable test subset:** which backend tests must pass for "done" — all (requires full infra) or unit-only?
6. **Repo path:** keep the leading-space directory name or rename before repair?

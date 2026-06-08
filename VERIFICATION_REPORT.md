# VERIFICATION_REPORT.md

Audit trail for the repair phase against the ratified `DISCOVERY.md` Definition of Done.
Ratified decisions: scope = **full local bring-up**; infra = **this repo's docker compose**; OpenAI key = **user-provided**; backend tests = **unit-only** (integration auto-skipped by conftest).
Environment deltas from discovery: Node v24.16.0 (✓ ≥20.9); default python3 is 3.14 (too new) → venv built with **python3.12**.

## DoD: `pip install -r requirements.txt` exits 0
- Command: `cd backend && python3.12 -m venv venv && ./venv/bin/pip install -r requirements.txt`
- Exit code: 0 — all pinned deps resolved on python3.12 with no conflicts
- Status: PASS

## DoD: `npm install` exits 0
- Command: `cd frontend && npm install`
- Exit code: 0
- Status: PASS

## DoD: 6 infra services healthy; `/health?check_services=true` all connected
- Command: `docker compose up -d` → all 6 containers report `(healthy)`
- Health: `{postgresql, milvus, minio, redis, celery_worker}` all `healthy`; overall `healthy`
- Status: PASS

## DoD: `./dev migrate` (Alembic) exits 0
- Command (underlying): `PATH="$PWD/venv/bin:$PATH" python -m scripts.setup.setup_postgres`
- Result: migrations completed; `Current: 012 (head)`
- Note: the script shells out to the `alembic` CLI, so the venv must be on PATH (the `./dev` wrapper does this automatically). Also ran `setup_minio` (buckets created) and `setup_milvus` (collections created) for the smoke test.
- Status: PASS

## DoD: `npm run build` exits 0
- Command: `cd frontend && npm run build`
- Result: exit 0; 14 routes prerendered as static content
- Status: PASS

## DoD: services run 30s without unhandled exception; frontend serves :3000
- Backend: `uvicorn main:app` up, /health=200 sustained >30s, no exceptions in log (only pkg_resources/datetime deprecation warnings)
- Celery: worker `ready`, responds to ping (health `celery_worker: healthy`)
- Frontend: `next start` Ready; `/` → 307 redirect (expected), `/dashboard` → 200, title "Near Perfect RAG — Cognitive Code"
- Status: PASS

## DoD: backend test subset passes (unit-only)
- Command: `python -m pytest` (integration tests auto-skipped unless RUN_INTEGRATION_TESTS=1)
- Result: **255 passed, 133 skipped, 0 failed** in 5.14s
- Note: pytest/pytest-asyncio are not declared in requirements; installed into the venv to run the suite.
- Status: PASS

## DoD: E2E smoke — ingest doc → `POST /v1/qa/ask` returns answer with ≥1 citation
- Requires: valid OPENAI_API_KEY + enabled gpt-5.2/gpt-5-mini models — both verified (key len 164; embeddings dim 3072; gpt-5.2 + gpt-5-mini reachable)
- Flow exercised: `POST /v1/ingest/document` (1 chunk, 1 page) → `POST /v1/embed/document` (graph_chunks_v2: 1 entity in Milvus) → `POST /v1/qa/ask`
- Result: answer `"The capital city of the fictional nation of Zorbia is Mirelle [..:1]. The Mirelle Tower is 472 meters tall [..:1]."`, model_id `gpt-5.2-2025-12-11`, **1 citation** with node_id:page marker. Factually correct vs. the source PDF.
- Notes:
  - **Embedding is a separate step** — `ingest_document_task` persists graph nodes to Postgres but does NOT embed; you must call `POST /v1/embed/document` (or `scripts/embed_all.py`) to populate Milvus before QA returns hits. The DoD smoke wording implied ingest alone made a doc queryable; in reality it's a documented two-step flow (the end assertion — cited answer — still holds).
  - **QA `doc_id` filter expects the canonical graph doc id**, not the upload `doc_id` (e.g. `npr_smoke.pdf-cea8ea7e3bf05e28`). Filtering by the upload id returned 0 seeds; using the graph doc id `f2e11b09…` or omitting `doc_id` works.
- Status: PASS

## NEW blocker found during repair: Celery prefork crashes on macOS
- Symptom: every ingest stayed `pending`; worker forked children died with `signal 6 (SIGABRT)` —
  `objc[...]: +[NSCharacterSet initialize] may have been in progress when fork() was called ... Crashing instead`.
  Adding `OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES` moved it to `signal 11 (SIGSEGV)` (native libs not fork-safe).
- Fix: run the worker with `--pool=solo` (no fork). `how_to_run.txt` already flags solo as required on Windows; it is the safe choice on macOS too. With solo, ingest completed in ~0.2s and the pipeline ran clean.
- Status: fixed (runtime flag); recommend documenting solo as the macOS default.

## Blockers from DISCOVERY.md
1. Docker infra footprint — status: **fixed** — all 6 services healthy
2. OPENAI_API_KEY / model access — status: **fixed** — key provided; embeddings + gpt-5.2 + gpt-5-mini all verified working; E2E smoke passed
3. Node version vs Next 16 — status: **fixed** — Node v24.16.0 (≥20.9); build + serve verified
4. Python dep install friction — status: **fixed** — built venv with python3.12; also pinned `setuptools<81` in requirements.txt (setuptools 82 dropped `pkg_resources`, which pymilvus 2.4.9 imports)
5. Migrations before use — status: **fixed** — at head (012)
6. Milvus server/client skew — status: **fixed (non-issue)** — pymilvus 2.4.9 connects to server 2.3.16 fine once pkg_resources restored
7. Leading-space repo path — status: **mitigated** — all paths quoted; rename deferred to follow-up
8. (NEW) Celery prefork crash on macOS — status: **fixed** — use `--pool=solo`; see section above

## Files changed during repair
- `backend/requirements.txt` — added `setuptools<81` pin (durable fix for the pymilvus/pkg_resources break)
- Created: `backend/.env` (from `.env.example`; OPENAI_API_KEY still placeholder), `backend/venv/` (gitignored), `frontend/node_modules/` + `frontend/.next/` (gitignored)

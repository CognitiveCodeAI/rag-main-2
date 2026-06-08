# IMPLEMENTATION_SUMMARY.md

Repair of the NPR-RAG repo against the ratified `DISCOVERY.md`. Outcome: **full local bring-up achieved; all 8 Definition-of-Done items PASS.** See `VERIFICATION_REPORT.md` for the per-assertion audit trail.

## What was broken / in the way
1. Docker daemon not running; 6 infra services not up.
2. No `OPENAI_API_KEY` / `backend/.env`.
3. Default `python3` is 3.14 — too new for the pinned dependency set.
4. `setuptools` 82 (pulled in by a fresh venv) removed `pkg_resources`, which `pymilvus 2.4.9` imports → import crash.
5. Test toolchain (`pytest`) undeclared, so the suite couldn't run.
6. Celery `--pool=prefork` crashes on macOS (fork + Obj-C → SIGABRT/SIGSEGV) → every ingest stuck `pending`.
7. Migrations shell out to the `alembic` CLI, which isn't on `PATH` unless the venv is activated.

## What changed (files)
- **`backend/requirements.txt`** — added `setuptools<81` pin (durable fix for the `pymilvus`/`pkg_resources` break).
- **`CLAUDE.md`** — added a "Verified local-run notes (macOS)" section capturing the python3.12 target, solo Celery pool, venv-on-PATH for migrations, the separate embed step, and the QA `doc_id` quirk. (Also the earlier `/init` accuracy improvements.)
- **New docs:** `DISCOVERY.md` (discovery phase), `VERIFICATION_REPORT.md` (audit trail), `IMPLEMENTATION_SUMMARY.md` (this file).
- **Generated, gitignored (not committed):** `backend/venv/`, `backend/.env`, `frontend/node_modules/`, `frontend/.next/`.
- **No business logic was changed.**

## How to run it now (macOS, verified)
```bash
# 0) one-time: env + deps
cp backend/.env.example backend/.env          # then set OPENAI_API_KEY in backend/.env
cd backend && python3.12 -m venv venv && ./venv/bin/pip install -r requirements.txt && cd ..
cd frontend && npm install && cd ..

# 1) infra (Docker Desktop must be running)
docker compose up -d                          # wait until all 6 containers are healthy

# 2) DB + storage init (venv must be on PATH — alembic is shelled out)
cd backend
PATH="$PWD/venv/bin:$PATH" ./venv/bin/python -m scripts.setup.setup_postgres
PATH="$PWD/venv/bin:$PATH" ./venv/bin/python -m scripts.setup.setup_minio
PATH="$PWD/venv/bin:$PATH" ./venv/bin/python -m scripts.setup.setup_milvus

# 3) services (three processes)
./venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 8000        # backend :8000
OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES ./venv/bin/celery -A app.worker worker --loglevel=info --pool=solo   # worker (solo on macOS!)
cd ../frontend && npm run start                                          # frontend :3000
```
Health: `curl 'http://localhost:8000/health?check_services=true'` → all services `healthy`.

## Validation performed (DoD)
| Assertion | Result |
|---|---|
| `pip install -r requirements.txt` exits 0 | PASS (python3.12) |
| `npm install` exits 0 | PASS |
| 6 infra services healthy; `/health?check_services=true` all connected | PASS |
| `./dev migrate` (Alembic) exits 0 | PASS (head 012) |
| `npm run build` exits 0 | PASS (14 routes) |
| Services run 30s clean; frontend serves :3000 | PASS |
| Backend test subset (unit-only) | PASS — 255 passed, 133 skipped, 0 failed |
| E2E smoke: ingest → cited answer | PASS — `gpt-5.2-2025-12-11`, 1 citation, correct facts |

## Main behavior verified end-to-end
Ingest a PDF → embed into Milvus → vector search + graph expansion → context packing → `gpt-5.2` answer with a page-level citation. Verified with a synthetic PDF containing facts that exist nowhere else ("Zorbia's capital is Mirelle", "Mirelle Tower is 472 m"); the model returned exactly those facts with citation markers.

## Remaining blockers
None blocking. All external dependencies (Docker, OpenAI key + models) were satisfied.

## DoD amendments accepted
None formally. One clarification surfaced and is recorded rather than silently changed: the E2E smoke required an intermediate `POST /v1/embed/document` call between ingest and QA (the DoD wording implied ingest alone made a doc queryable). The end assertion — a cited answer — still holds, so this is logged as a note in `VERIFICATION_REPORT.md`, not a rewrite of the DoD.

## Follow-up work (separate from the functional repair)
1. **Auto-enqueue embedding after ingest** (or document the two-step flow in the API), so a freshly ingested doc is queryable without a manual `/v1/embed/document` call.
2. **Default the Celery pool to `solo` on macOS** in `run.py` / `./dev` (or set `OBJC_DISABLE_INITIALIZE_FORK_SAFETY` + a fork-safe pool), so ingestion works out of the box.
3. **Add a `requirements-dev.txt`** (or a `[dev]` extra) pinning `pytest`/`pytest-asyncio` so `./dev test` works on a clean checkout.
4. **Pin a supported Python** (e.g. a `.python-version` of 3.12) so `python3` doesn't default to an unsupported 3.14.
5. **Modernize `datetime.utcnow()`** usages (deprecation warnings in `main.py`, `routes/ingest.py`).
6. Consider renaming the repo directory to drop the leading space in `" NPR-RAG"`.
7. QA `doc_id` filtering: accept the upload `doc_id` (resolve to graph doc id) for ergonomics, matching how `/v1/embed/document` resolves identity.

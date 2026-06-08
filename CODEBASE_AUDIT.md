# Principal Engineer Codebase Audit

> Read-only, evidence-based audit of NPR-RAG (Near-Perfect RAG). No code was changed. Performed 2026-06-07/08.
> **Confidence tags:** `[VERIFIED]` = re-observed in a tool call during *this* audit pass · `[INFERRED]` = strong single-source evidence (incl. findings surfaced by a sub-agent with file:line refs but not personally re-run this pass) · `[ASSUMED]` = best guess. Grep-derived counts are directional estimates with the pattern stated.

---

## 1. Executive Summary

**What this codebase appears to do.** A production-grade graph-RAG system for document question-answering with evidence-based, page-level citations. Documents are parsed → chunked (page-bounded) → modeled as graph nodes/edges → embedded (OpenAI `text-embedding-3-large`, 3072-dim) → stored across PostgreSQL (metadata/graph), Milvus (vectors), and MinIO (blobs). QA flow: embed question → Milvus vector search → multi-stage ACL filtering → graph expansion → LLM reranking → context packing → `gpt-5.2` answer with citations + conflict detection. An optional multi-tenant Access Control Layer gates retrieval. `[VERIFIED]` (README, runner.py, pipeline.py, acl/, config.py)

**Overall health: Mixed — strong engineering core, undermined by an unsecured perimeter and near-absent CI verification.** The retrieval/graph/citation core is sophisticated and thoughtfully built: ACL is enforced *inside* retrieval (not just at routes), content-hash dedup is idempotent with atomic upserts, there's conflict detection, a reranker gate, and a self-healing monitor subsystem. But the **authentication perimeter is effectively absent in the default configuration**, and **CI exercises almost none of the security-critical behavior**.

**Recommendation: Maintain & harden — do NOT rewrite.** The hard, valuable parts (graph RAG, citations, ACL-in-retrieval, idempotent ingestion) are done well and would be expensive and risky to reproduce. The serious problems are localized to the auth perimeter, CI/test gating, and a handful of reliability seams — all incrementally fixable in days. Empirically, large rewrites touch more files and fail more often than incremental work; there is no evidence a rewrite would be cheaper or safer here. The maintain call is **not** propped up by test coverage (coverage is in fact a top risk) — it rests on the structural quality of the code that was read this pass.

**A load-bearing caveat on test coverage.** I ran the default unit suite this session (255 passed, 133 skipped) and the frontend build (green), and exercised the full ingest→embed→cited-answer path end-to-end. But the suites that would prove the *security* claims (ACL isolation, citation-leak canaries, ingestion e2e) are skipped by default and do **not** run in CI. So "the app works" is `[VERIFIED]` for the happy path; "authorization is correct" is **not** verified by tests and must be treated as unproven until those suites run.

### Top 5 risks
1. **Unauthenticated ingestion with client-supplied tenant/ACL fields** — anyone can inject documents into any tenant. `[VERIFIED ingest.py:697-708]`
2. **Identity trusted from unsigned headers** (`X-Tenant-Id`/`X-User-Id`/`X-Roles`) — even with ACL on, a client spoofs any tenant/role. `[VERIFIED resolver.py:18-39]`
3. **ACL disabled by default** (`acl_enabled=False`) — zero authorization out of the box. `[VERIFIED config.py:106]`
4. **CI verifies almost nothing** — only `test_acl_unit.py` (mocked) + a syntax check run; ACL e2e/canary, ingestion e2e, and all frontend tests never run. `[VERIFIED ci.yml]`
5. **No LLM retry + unvalidated citations** — a single 429/timeout fails the answer; model-emitted node_ids not in context become "unresolved" citations instead of being dropped. `[VERIFIED openai_client.py:245-247, runner.py:1305-1462]`

### Top 5 quick wins
1. Add an auth dependency to ingest/process routes; derive `tenant_id` from identity, never the form body. `[S]`
2. Default `acl_enabled=True` (fail-closed), or refuse to boot in prod with ACL off. `[S]`
3. Add `RUN_INTEGRATION_TESTS=1` + ephemeral Postgres/Milvus to CI; add `npm run test` + `tsc --noEmit`. `[M]`
4. Drop citations whose `node_id` ∉ `context_node_ids` (already computed at runner.py:1216). `[S]`
5. Wrap the two OpenAI calls in bounded exponential-backoff retry. `[S]`

---

## 2. Repository Map

| Path | Purpose |
|---|---|
| `backend/` | FastAPI API server (~44k LOC Python, 208 files). Entry: `backend/main.py`. `[VERIFIED]` |
| `backend/app/routes/` | API endpoints: `qa, ingest, embed, retrieve, documents, prompts, acl, settings`. `[VERIFIED]` |
| `backend/app/qa/runner.py` | QA pipeline orchestrator — **2847 lines, single `QARunner` class**. `[VERIFIED]` |
| `backend/app/graph/` | Ingestion pipeline (`pipeline.py` 857 LOC), chunker, nodes, edges, `vector_index.py`, content registry. `[VERIFIED]` |
| `backend/app/acl/` | Access Control Layer: `enforcer, policy, resolver, postgres_filter, audit, dependencies`. `[VERIFIED]` |
| `backend/app/tasks/` | Celery tasks: `ingest, embed, index, embed_nodes`. `[VERIFIED]` |
| `backend/app/ocr/` | OCR clients: `openai_client` (default, gpt-5-mini), `ollama_client`. `[VERIFIED]` |
| `backend/app/monitor/` | Self-healing monitor: observer, checks, remediation, JSONL logger. `[VERIFIED]` |
| `backend/app/{llm,embeddings,vectordb,storage,metadata,services}/` | OpenAI client, embedding client, Milvus client, MinIO client, metadata extraction, highlighting. `[VERIFIED]` |
| `backend/alembic/` | DB migrations (head = 012). `[VERIFIED]` |
| `backend/tests/` | 60 test files; 19 are integration (skipped unless `RUN_INTEGRATION_TESTS=1`). `[VERIFIED]` |
| `frontend/` | Next.js 16 + React 19 app (~12.6k LOC, 58 .tsx + 21 .ts). Entry: `frontend/src/app/`. `[VERIFIED]` |
| `frontend/src/lib/api.ts` | API client (all fetch calls + types). `[VERIFIED]` |
| `contracts/` | `@npr/contracts` shared schema package (python/ + schemas/). Not imported by frontend/backend src — codegen source-of-truth. `[INFERRED]` |
| `docker-compose.yml` | 6-service dev infra (postgres15, etcd, minio×2, milvus 2.3.16, redis7). `[VERIFIED]` |
| `dev`, `run.py`, `setup.sh/.ps1` | Dev orchestration CLIs. `[VERIFIED]` |
| `.github/workflows/ci.yml` | CI: backend syntax+1 test file, frontend lint+build. `[VERIFIED]` |

**Deprioritize:** `backend/venv/`, `frontend/node_modules/`, `frontend/.next/` (gitignored build artifacts); root `*.png` screenshots; `backend/tests/eval/run_qa_eval.py` (2840 LOC eval harness, not core runtime).

---

## 3. Architecture Overview

**Components.** FastAPI app (sync + async routes) → Celery workers (ingestion/embedding) over Redis → PostgreSQL (relational: documents, jobs, graph nodes/edges, citation snapshots) + Milvus (vector collections `graph_chunks_v2`, `graph_figures_v2`, `graph_tables_v2`, legacy `*_v1`) + MinIO (`npr-corpus`, `npr-traces` buckets). OpenAI is called for embeddings, QA generation (`gpt-5.2` Responses API), reranking (`gpt-4o-mini` direct HTTP), and OCR (`gpt-5-mini`). `[VERIFIED]`

**Control/data flow.**
```
Ingest:  POST /v1/ingest/document → ingest_document_task (Celery)
         → parse → page-bounded chunk → create graph nodes/edges (+figure OCR via gpt-5-mini)
         → persist to Postgres  [STOPS HERE — no vectors yet]
Embed:   POST /v1/embed/document → embed_nodes_task → OpenAI embeddings → Milvus index
QA:      POST /v1/qa/ask → embed → Milvus search → ACL filter → graph expand
         → rerank (gpt-4o-mini) → conflict detect → pack context → gpt-5.2 answer + citations → ACL filter citations
```
`[VERIFIED runner.py, pipeline.py, tasks/]`. **Critical seam:** ingestion and embedding are decoupled — ingest alone does not make a doc queryable; the UI calls both endpoints in sequence. `[VERIFIED tasks/ingest.py:23-196 has no embed trigger; embed is separate at embed.py:152]`

**External dependencies.** PostgreSQL 15, Milvus 2.3.16 (server) / pymilvus 2.4.9 (client), MinIO, Redis 7, OpenAI API. `opensearch-py` and `neo4j` are in requirements but only `vectordb/milvus_client.py` is wired — OpenSearch/Neo4j appear to be optional/experimental backends. `[VERIFIED]`

**Identity model.** A reverse-proxy pattern: the app reads `X-Tenant-Id/X-User-Id/X-Roles/X-Groups` headers and trusts them. There is **no application-level authentication** (no JWT, session, or API key). `[VERIFIED resolver.py:18-39]`

**Deployment model.** Dev: `docker compose` + `./dev up` or `run.py` (uvicorn + Celery + Next). No production deployment manifests in-repo beyond `backend/docs/DEPLOYMENT_GUIDE.md`; compose is dev-oriented (default creds, localhost). `[VERIFIED]`

---

## 4. Findings

### Critical

**C-1. Unauthenticated document ingestion with client-controlled tenant/ACL fields**
- Severity: Critical · Confidence: `[VERIFIED]`
- Evidence: `routes/ingest.py:697-708` — `ingest_document` has no `Depends(get_entitlements)` and accepts `tenant_id`, `visibility`, `allowed_roles/groups/users` as `Form(...)`. `get_entitlements` is wired only on read endpoints (`ingest.py:831`, `:981`). Same gap on `/metadata-preview` (`:474`) and `/process` (`:550`).
- Why it matters: Any unauthenticated caller can inject documents into any tenant and stamp arbitrary ACLs on them — data poisoning of QA results, cross-tenant pollution, storage abuse. Combined with C-2/C-3, there is no perimeter at all by default.
- Suggested fix: Require an auth dependency on all write routes; source `tenant_id` from the authenticated identity; reject client-supplied tenant.
- Risk of fixing: Low.

**C-2. Identity trusted from unsigned request headers (no token validation)**
- Severity: Critical · Confidence: `[VERIFIED]`
- Evidence: `acl/resolver.py:18-39` — `tenant_id`, `user_id`, roles, groups read directly from `X-*` headers; no JWT/signature/HMAC/decode anywhere in the resolver. Header comments call it the "reverse proxy pattern."
- Why it matters: Even with ACL **enabled**, a direct client sets `X-Roles: admin` / `X-Tenant-Id: <victim>` and bypasses all isolation. The whole ACL design rests on an upstream proxy that is not present in this repo and is trivially bypassed if the API is reachable directly.
- Suggested fix: Validate a signed token (JWT/OIDC) and derive entitlements from verified claims; if a proxy injects identity, ensure the app is not directly reachable and reject the trusted headers from untrusted sources (mTLS / shared secret).
- Risk of fixing: Medium (touches every authed request).

### High

**H-1. ACL disabled by default (`acl_enabled=False`)**
- Severity: High · Confidence: `[VERIFIED config.py:106]`
- Evidence: `acl_enabled: bool = False`; when off, `get_entitlements` returns `None` and `ACLPostgresFilter` returns the unfiltered query. Startup only logs a `warning`.
- Why it matters: A fresh/misconfigured deployment has no authorization. Fail-open is the wrong default for a multi-tenant system.
- Suggested fix: Default `True` (fail-closed); make disabling require an explicit, loud opt-out; refuse to start in a "prod" profile with ACL off.
- Risk of fixing: Low (config + a startup guard).

**H-2. CI does not verify security-critical behavior**
- Severity: High · Confidence: `[VERIFIED ci.yml]`
- Evidence: backend job = `pip install` + `compileall` + `pytest tests/test_acl_unit.py -q` (one mocked file). Frontend job = `npm ci` + `lint` + `build`. No integration tests (ACL e2e/canary, ingestion e2e all skipped by `conftest.py`), no `npm run test`, no `mypy`/`tsc --noEmit`.
- Why it matters: The tests that actually prove tenant isolation and citation-leak prevention (`test_acl_canary.py`, `test_acl_e2e.py`) never run in CI. Regressions in the security core would merge undetected.
- Suggested fix: Add a CI job that runs `RUN_INTEGRATION_TESTS=1` against ephemeral Postgres+Milvus (service containers / testcontainers); add frontend test + typecheck steps; make these required checks via branch protection.
- Risk of fixing: Low–Medium (CI work, slower pipeline).

**H-3. No retry/backoff on any OpenAI call**
- Severity: High · Confidence: `[VERIFIED]`
- Evidence: `llm/openai_client.py:245-247` (answer generation: `except Exception: ... raise`, no backoff); `qa/runner.py:303` reranker `max_retries=0  # fail fast to fallback`; reranker uses a hardcoded 5s timeout via direct `httpx` (`runner.py:~1886`). `[INFERRED for the exact reranker line — surfaced by sub-agent, retry-absence VERIFIED]`
- Why it matters: A single transient 429/timeout fails the user's answer outright. OpenAI rate-limits are routine at load.
- Suggested fix: Bounded exponential backoff (e.g. tenacity, 3 tries) on both calls; categorize errors (429 vs timeout vs 5xx) for observability.
- Risk of fixing: Low.

**H-4. Citations are not validated against retrieved context (hallucinated-citation risk)**
- Severity: High (for a citations product) · Confidence: `[VERIFIED]`
- Evidence: `runner.py:1216` computes `context_node_ids`, but it's used only as a **fallback lookup** (`:1305-1306`). A model-emitted `[node_id:page]` not in context resolves to `resolve_status:"unresolved"` with `evidence_confidence=0.0` (`:1431`, `:1462`) and is **still returned**. The prompt says "must not hallucinate" (`:442`) but nothing enforces it programmatically.
- Why it matters: The core product promise is *evidence-based* citations. Returning unresolved/hallucinated citations erodes the central trust guarantee.
- Suggested fix: After extraction, drop (or hard-flag) any citation whose `node_id ∉ context_node_ids`; surface a count of dropped citations for monitoring.
- Risk of fixing: Low (may reduce citation counts, improves integrity).

**H-5. No transactional reconciliation between Postgres nodes and Milvus vectors**
- Severity: High · Confidence: `[INFERRED]` (sub-agent, with refs `pipeline.py:382/612`, `tasks/embed_nodes.py:351-384`; not re-run this pass)
- Evidence: nodes are committed to Postgres in ingestion; vectors are indexed later in a separate task. If embedding partially fails, status becomes `partial`/`failed` but Postgres nodes remain — orphaned nodes with no vectors and no reconciliation job.
- Why it matters: Silent retrieval gaps (a doc looks ingested but isn't fully queryable). I personally hit the decoupling live: a raw ingest produced 0 searchable nodes until a separate embed ran.
- Suggested fix: Track an explicit `embedding_status` on the document; add a reconciliation/sweeper that finds nodes lacking vectors and re-enqueues embedding.
- Risk of fixing: Medium.

**H-6. Jobs can stick in `processing`/`pending` with no terminal state**
- Severity: High · Confidence: `[INFERRED]` (sub-agent refs `tasks/ingest.py:79-147`; I *did* observe a job sit in `pending` for 2 min live when the worker was crashing — consistent)
- Evidence: with `task_acks_late=True`, a worker crash requeues the task only after the broker visibility timeout; meanwhile `job.status` stays `processing` with no heartbeat or dead-job sweeper.
- Why it matters: Users (and the UI) cannot distinguish "working" from "dead." This is exactly what looked like the app being "stuck" earlier.
- Suggested fix: Add a job heartbeat + a sweeper that marks stale jobs `failed`; expose elapsed/last-update in the job API and UI.
- Risk of fixing: Medium.

**H-7. Serial, unbounded figure OCR cost/latency**
- Severity: High (cost/ops) · Confidence: `[INFERRED]` (sub-agent; I observed ~19 serial `gpt-5-mini` OCR calls of 5–30s each on one 270-page doc live — consistent)
- Evidence: figure regions OCR'd one-by-one via `gpt-5-mini` with no batching, caching, or spend cap (`graph/nodes.py:302-324`, `ocr/openai_client.py`).
- Why it matters: Large documents take many minutes and incur unbounded per-figure API spend; no guardrail.
- Suggested fix: Batch/parallelize OCR (bounded concurrency), cache by figure hash, optional OCR, and a per-doc spend cap.
- Risk of fixing: Medium.

**H-8. `file://` source read without path canonicalization (traversal)**
- Severity: High (conditional) · Confidence: `[VERIFIED]` for the code, `[INFERRED]` for exploitability
- Evidence: `routes/documents.py:705-708` — `file_path = source_uri.replace("file://","")` then `open(file_path)`, no `realpath`/allow-list check.
- Why it matters: If an attacker can create/influence a document with `source_uri="file:///etc/passwd"` (plausible given unauthenticated ingest, C-1), this reads arbitrary host files. Standard uploads store to MinIO (not `file://`), so exploitability depends on a path that sets a `file://` URI — hence conditional.
- Suggested fix: Canonicalize and restrict to an allow-listed root; reject `..` and non-allowed prefixes.
- Risk of fixing: Low.

### Medium

- **M-1. Insecure default credentials baked into config** — `db_password="ragpass"`, `minio_access_key/secret="minioadmin"` (`config.py:44,48,49`); also in `.env.example`. If env isn't set in prod, weak creds become live. Use empty defaults + fail-fast. `[VERIFIED]`
- **M-2. User questions logged at INFO** — `runner.py:626-633` logs truncated question text at INFO; in a multi-tenant system questions may carry PII. Move to DEBUG or log length/hash only. `[INFERRED]`
- **M-3. TOCTOU dedup race in `/ingest/document`** — single duplicate check before enqueue vs the double-check in `/process`; concurrent identical uploads can both proceed. `[INFERRED ingest.py:740-806]`
- **M-4. OCR failure is silent per-figure** — `graph/nodes.py:302-324` swallows OCR errors and continues with empty text; figures lose searchable content with no health signal. `[INFERRED]`
- **M-5. Constraint filters not re-applied on fallback search** — `runner.py:754-769` retries without the metadata filter and doesn't re-validate, so a "after 2020" query can return 2019 nodes. `[INFERRED]`
- **M-6. Monitor state is single-process JSON** — `app/monitor/state.py`; multi-worker deployments get inconsistent circuit-breaker/dedupe state. Move to Redis. `[INFERRED]`
- **M-7. No correlation/request IDs across FastAPI→Celery** — debugging async jobs is hard; add request-id middleware + task context propagation. `[INFERRED]`
- **M-8. Frontend: no fetch timeouts; polling without circuit-breaker** — `lib/api.ts` fetches lack `AbortController`; `health-indicator.tsx:40`, `processing/page.tsx:260` poll on intervals that don't stop on repeated failure. `[INFERRED]`
- **M-9. Frontend: `pollIngestJob` missing a terminal state** — `api.ts:605` doesn't treat `skipped_alias` as terminal (the embed poller does at `:655`), so some ingests can spin forever in the UI. `[INFERRED]`
- **M-10. Backend errors not consistently surfaced to users** — `api.ts:350` `APIError.detail` may be a raw blob/stack; no `formatAPIError`. `[INFERRED]`

### Low

- **L-1. CORS allows wildcard methods/headers** — `main.py:61-66`; mitigated by localhost-scoped `cors_origins` (`config.py:33`), so low impact. Tighten methods/headers anyway. `[VERIFIED]`
- **L-2. `QARunner` is a 2847-line god-object** (24 methods, two pipelines, duplicated retrieval logic). Maintainability/testability drag, not a defect. `[VERIFIED file length]`
- **L-3. Reranker model `gpt-4o-mini` hardcoded** while answers use `gpt-5.2`; expose as config. `[INFERRED runner.py:~1876]`
- **L-4. `datetime.utcnow()` deprecations** in `main.py`, `routes/ingest.py` (surfaced as warnings when I ran the suite). `[VERIFIED via pytest warnings this session]`
- **L-5. Icon buttons below 44px** (`button.tsx` `icon`=36px, `icon-xs`=24px) — fine for desktop/cursor, a concern only if used on touch devices. `[INFERRED]`
- **L-6. `NEXT_PUBLIC_API_URL` read in 3 places** (`api.ts:5`, `chat-client.tsx:792`, `html-viewer.tsx:34`) — centralize. `[INFERRED]`
- **L-7. Accessibility polish** — command-menu trigger lacks `aria-label`; inline citation buttons lack descriptive labels; loading `aria-busy` missing on the doc selector. Radix primitives cover dialogs/select/collapsible; gaps are in hand-rolled bits. `[INFERRED]`

---

## 5. Security Review

- **Secrets:** loaded via pydantic `BaseSettings` from env/`.env`. No secrets found logged or hardcoded *as live credentials*, but **insecure dev defaults** (`ragpass`, `minioadmin`) are baked in and used if env is unset (M-1). `OPENAI_API_KEY` masked appropriately in summaries. No secrets manager / rotation. `[VERIFIED config.py; INFERRED for prod secret handling]`
- **AuthN:** none at the application layer — relies entirely on trusted upstream headers (C-2). `[VERIFIED]`
- **AuthZ:** a genuinely good design (multi-stage ACL filtering inside retrieval — `runner.py:734,766,780,871,1245` — so denied content never reaches the LLM) sitting on top of a non-existent perimeter (C-1/C-2/H-1). The ACL is well-built but trivially bypassed by spoofed identity or unauthenticated ingest. The scattered enforcement points are also a bypass risk if a new retrieval path forgets one. `[VERIFIED design; INFERRED bypass-on-new-path]`
- **Input handling:** file uploads have size config (`upload_max_file_size_mb`) and PDF-only default; `file://` read lacks canonicalization (H-8). Search uses ORM `ilike` with no length cap (DoS-via-pattern, low). No raw SQL string-building observed (SQLAlchemy ORM throughout). No `subprocess`/`os.system` command execution observed in request paths. `[VERIFIED/INFERRED]`
- **Dependency CVEs:** not scanned this pass (no SCA in repo). Recommend adding `pip-audit` + `npm audit`/Dependabot. `[ASSUMED — not run]`
- **Logging/PII:** questions logged at INFO (M-2); no tenant context in logs.

---

## 6. Reliability and Operations Review

- **Failure modes:** Postgres↔Milvus non-transactional (H-5); jobs can stick (H-6); per-figure OCR failures silent (M-4); MinIO highlight-artifact write is non-fatal (acceptable). `[INFERRED]`
- **Timeouts/retries:** no retry/backoff on LLM calls (H-3); Celery has sane `task_time_limit=3600`, `task_soft_time_limit=3000`, `acks_late=True`, `reject_on_worker_lost=True`, `max_retries=3` with exponential backoff. `[INFERRED worker.py:29-33]`
- **Concurrency / platform:** Celery `--pool=prefork` **crashes on macOS** (fork + Obj-C → SIGABRT, then native libs SIGSEGV) — `[VERIFIED this session via worker logs]`; `--pool=solo` works. This is a dev-platform issue but bites anyone onboarding on a Mac, and it silently leaves jobs `pending`.
- **Observability:** standard logging, no correlation IDs (M-7); a capable `monitor/` subsystem (health checks + auto-remediation + JSONL) but single-process state (M-6). `/health?check_services=true` does real connectivity checks to all four data services — `[VERIFIED this session: returns healthy]`.
- **Deployment fragility:** compose is dev-only (default creds, `minio:latest` unpinned, mixed MinIO versions). No prod manifests/secrets strategy in-repo.

---

## 7. Testing Assessment

- **What exists:** 60 backend test files (~288 test functions by `grep "def test"`, `[INFERRED]`), including strong-looking ACL canary/e2e and ingestion/graph e2e suites; 1 real frontend test (`source-viewer/evidence.test.ts`, 4 cases). `[VERIFIED file inventory]`
- **What runs by default:** `conftest.py:50-63` skips 19 integration files unless `RUN_INTEGRATION_TESTS=1`. I **ran** the default suite this session: **255 passed, 133 skipped, 0 failed** `[VERIFIED]`. So the *unit* layer is green and non-trivial.
- **What's actually protected vs not:** unit tests cover models/schemas/parsers/ACL-unit-logic. The **security-critical** behaviors — real Postgres ACL filtering, cross-tenant isolation, citation-leak canaries, ingestion e2e — live **only** in the skipped/integration suites and run in **neither** default test nor CI (H-2). `test_acl_unit.py` (CI's only test) is mocked-DB and does not prove enforcement.
- **Did I run them?** Default unit suite: yes `[VERIFIED]`. Integration/ACL e2e/canary: **no** — not run this pass; their protection is `[INFERRED — tests exist and read like they cover X, not executed]`.
- **Most valuable tests to wire into CI first (in order):** `test_acl_canary.py` (leak prevention), `test_acl_e2e.py` (tenant isolation), `test_ingestion_e2e.py` (upload→queryable), then the frontend `evidence.test.ts` + a chat/api smoke. The bar isn't "add tests" — these tests *exist*; they just need infra + a CI job to run.

---

## 8. Dependency and Build Assessment

- **Backend (`requirements.txt`):** pinned (good). Two deliberate constraints: `marshmallow<4` (pymilvus needs v3) and — added this session — `setuptools<81` (pymilvus 2.4.9 imports `pkg_resources`, removed in setuptools 81) `[VERIFIED this session]`. One unpinned range: `jsonschema>=4.20.0` (reproducibility nit). `pytest`/`pytest-asyncio` are **used but undeclared** (installed ad-hoc in CI and by me this session) — add a `requirements-dev.txt`. No Python lockfile (pinned reqs only). `[VERIFIED]`
  - *Where deps run:* all prod-runtime (FastAPI/SQLAlchemy/pymilvus/celery/openai) except pytest (test-only). `opensearch-py`/`neo4j` declared but effectively unused at runtime. `[VERIFIED imports]`
- **Frontend (`package.json`):** `package-lock.json` present; `next`/`react`/`react-dom` exact-pinned, others caret ranges. No `engines` field — Next 16 needs Node ≥20.9 (CI uses Node 20; my machine Node 24 works). `[VERIFIED]`
- **Runtime/version assumptions:** CI uses **Python 3.11**; local needs **3.12** (3.11 absent on this machine, default `python3` is 3.14 which is too new for the pinned stack) `[VERIFIED this session]`. This 3.11-CI / 3.12-local / 3.14-system spread is a reproducibility hazard — pin a supported interpreter (`.python-version`/pyproject).
- **Build reproducibility:** frontend good (lockfile + `npm ci`); backend weaker (no lock, version spread). Frontend build verified green this session (14 routes). `[VERIFIED]`
- **No SCA** (pip-audit/npm-audit/Dependabot) — add it.

---

## 9. Refactoring Opportunities

**Low-risk cleanup** (no behavior change, minimal test exposure):
- Centralize `NEXT_PUBLIC_API_URL` (L-6); fix `datetime.utcnow()` deprecations (L-4); pin `jsonschema`, add `requirements-dev.txt`, add `engines`/`.python-version`. Prereq: none.

**Medium-risk refactors** (need tests first):
- Extract `CitationHydrator`, `Reranker`, and `PropagationSafetyRunner` out of the 2847-line `QARunner` (L-2). Prereq: characterization tests around QA output (citations, seed selection) before splitting.
- Centralize ACL enforcement into a single guarded search wrapper so new retrieval paths can't skip it (Security §5). Prereq: ACL canary suite running in CI.

**High-risk architectural changes** (defer until safety rails exist):
- Make ingest→embed atomic or add a reconciliation sweeper (H-5). Prereq: embedding-status tracking + integration tests.
- Replace header-trust identity with verified tokens (C-2). Prereq: decide IdP/proxy model; this is an epic, not a single PR.

---

## 10. Modernization Plan

**Phase 0 — Stabilize & document (days).** Pin Python (3.12) and Node engines; add `requirements-dev.txt`; document the macOS `--pool=solo` requirement and the ingest→embed two-step (partially captured in `CLAUDE.md` already this session); add `pip-audit`/`npm audit`. Objective: reproducible setup. Risk: Low.

**Phase 1 — Safety rails (1–2 weeks).** Stand up integration CI (ephemeral Postgres+Milvus, `RUN_INTEGRATION_TESTS=1`) running ACL canary/e2e + ingestion e2e; add frontend `vitest` + `tsc --noEmit` + backend `mypy`; make them required checks. Objective: the security core is continuously verified. Risk: Low–Medium. **This phase is the prerequisite for trusting any later refactor.**

**Phase 2 — Close the perimeter & reliability seams (2–4 weeks).** Auth dependency on write routes + tenant-from-identity (C-1); fail-closed ACL default (H-1); token-verified identity (C-2); LLM retry/backoff (H-3); citation-in-context validation (H-4); job heartbeat/sweeper (H-6); embedding reconciliation (H-5). Objective: production-safe. Risk: Medium.

**Phase 3 — Modernize architecture (ongoing).** Decompose `QARunner` (L-2); centralize ACL enforcement; batch/cache OCR with spend caps (H-7); Redis-backed monitor state (M-6); correlation IDs (M-7). Objective: maintainable + cost-controlled at scale. Risk: Medium.

---

## 11. Top 10 Action Items

| # | Priority | Action (stable title) | Impact | Effort | Risk | Files | Acceptance check |
|---|---|---|---|---|---|---|---|
| 1 | P0 | **Authenticate write routes; derive tenant from identity** | Closes the open ingestion perimeter | M | Med | `routes/ingest.py`, `acl/dependencies.py` | Unauthenticated `POST /v1/ingest/document` returns 401; `tenant_id` form field is ignored in favor of identity |
| 2 | P0 | **Verify identity from signed tokens (replace header-trust)** | Stops tenant/role spoofing (epic) | L | Med | `acl/resolver.py`, new auth middleware | A request with forged `X-Roles: admin` and no valid token is denied admin scope |
| 3 | P0 | **Default ACL to fail-closed** | No silent zero-authz deployments | S | Low | `config.py:106`, startup guard | App refuses to boot in prod profile with `acl_enabled=False`; default is `True` |
| 4 | P0 | **Run ACL/ingestion integration tests in CI** | Continuously proves isolation | M | Low | `.github/workflows/ci.yml`, service containers | CI job runs `RUN_INTEGRATION_TESTS=1` incl. `test_acl_canary.py` green on PRs; required check |
| 5 | P1 | **Validate citations against `context_node_ids`** | Restores evidence guarantee | S | Low | `qa/runner.py` (~1305), `llm/openai_client.py:375-423` | A response containing a node_id not in context returns 0 such citations (unit test) |
| 6 | P1 | **Add bounded retry/backoff to OpenAI calls** | Survives 429/timeout | S | Low | `llm/openai_client.py:245`, `qa/runner.py:303` | Injected 429 then success yields an answer; ≤3 attempts |
| 7 | P1 | **Job heartbeat + stale-job sweeper** | Distinguish working/dead | M | Med | `tasks/*`, `db/models.py`, `routes/ingest.py` | A killed-mid-job task transitions to `failed` within the heartbeat window, not stuck `processing` |
| 8 | P1 | **Embedding reconciliation + status** (epic: spans ingest/embed/QA) | No silent un-queryable docs | M | Med | `db/models.py`, `tasks/embed_nodes.py`, sweeper | Query finds nodes lacking vectors; sweeper re-embeds; doc reports `embedding_status=complete` |
| 9 | P2 | **Batch/cache figure OCR + spend cap** | Cuts ingest latency & cost | L | Med | `graph/nodes.py:302`, `ocr/openai_client.py` | A 270-page doc ingests with bounded-concurrency OCR; per-doc OCR spend capped/logged |
| 10 | P2 | **Frontend fetch timeouts + polling circuit-breaker + terminal states** | UI can't hang/spin forever | M | Low | `lib/api.ts:605`, `health-indicator.tsx:40`, `processing/page.tsx` | Stalled request aborts at 30s; poller stops after N consecutive failures; `skipped_alias` ends polling |

---

## 12. Open Questions

1. **What enforces the trusted-header boundary in production?** The ACL design assumes an upstream proxy injects `X-*` identity and the app isn't directly reachable. Is there such a proxy, and is direct access to `:8000` network-blocked? This determines whether C-1/C-2 are "theoretical" or live. `[VERIFIED the assumption; deployment unknown]`
2. **Is ACL intended to be on in production?** If yes, H-1's fail-open default is a latent incident; if the product is single-tenant, much of the ACL surface is moot — which is it?
3. **Is figure OCR required for the target documents, or opt-in?** It dominates ingest cost/latency (H-7); the answer changes the Phase-3 priority.
4. **Are OpenSearch/Neo4j live backends or dead code?** They're in `requirements.txt` with connection tests but only Milvus is wired — keep (and test) or remove to cut dependency surface.
5. **What is the production deployment target?** No prod manifests in-repo; the maintain-vs-harden plan's Phase 0/1 specifics (secrets manager, CI infra) depend on it.

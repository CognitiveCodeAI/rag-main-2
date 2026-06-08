# NPR-RAG Remediation Plan

> Derived directly from `CODEBASE_AUDIT.md` (2026-06). This is the executable companion to the audit: it turns the audit's findings (`C-1`, `H-2`, …) and Top-10 action items into sequenced, PR-sized work with explicit dependencies and a runnable Definition of Done per task.
> **It does not introduce new findings** — every task traces back to an audit finding ID. Where the audit tagged something `[INFERRED]` (not re-run this pass), the task includes a "confirm first" step so we verify before changing code.

## How to use this document
- Work is grouped into five **workstreams (WS-A…WS-E)** mapping to the audit's Modernization phases.
- Each task has: linked finding · what/why · files · approach (kept PR-sized) · **Acceptance** (the gate that closes it) · dependencies · effort (S/M/L) · risk.
- Follow the **Execution Sequence** at the bottom — it encodes the one hard ordering rule below.

## The one hard ordering rule
**WS-B (safety rails / integration CI) gates every refactor.** The audit's central finding (`H-2`) is that the security-critical suites — ACL canary, ACL e2e, ingestion e2e — exist but never run. Until they run in CI, we have no regression net. Therefore:
- The **fail-closed/auth quick wins** (WS-C waves 1) may ship in parallel with standing up CI — they're additive and low-risk.
- The **refactors** (centralizing ACL enforcement, decomposing `QARunner`) must **not** start until the canary suite is green in CI.

## Guiding principles
1. **Fail-closed by default** — security defaults deny; opting out is loud and explicit.
2. **Tests before refactor** — no structural change to ACL or QA until its characterization/integration tests run in CI.
3. **Small, reversible PRs** — each task is one PR where possible; tasks marked *(epic)* are split into the listed slices.
4. **Confirm `[INFERRED]` findings before coding** — the audit flagged which findings were not re-run this pass; verify, then fix.

---

## WS-A — Stabilize & reproducibility  *(Audit Phase 0 · no dependencies · do first/parallel)*

### A1. Pin the toolchain (Python 3.12, Node ≥20.9)
- Finding: §8 version spread (CI 3.11 / local 3.12 / system 3.14). Confidence in audit: `[VERIFIED]`.
- Files: `backend/.python-version` (new) or `pyproject.toml`; `frontend/package.json` (`engines`); `.github/workflows/ci.yml` (align Python to 3.12).
- Approach: add `.python-version` = `3.12`; add `"engines": { "node": ">=20.9" }`; bump CI `setup-python` to 3.12.
- Acceptance: `python --version` resolves 3.12 in a fresh `./dev init`; CI Python job runs on 3.12 and stays green.
- Effort: S · Risk: Low

### A2. Declare the test toolchain
- Finding: §8 — `pytest`/`pytest-asyncio` used but undeclared (installed ad-hoc).
- Files: `backend/requirements-dev.txt` (new); `ci.yml` (install from it).
- Approach: create `requirements-dev.txt` with `pytest`, `pytest-asyncio`, and (for A4) `mypy`; CI installs it instead of `pip install pytest`.
- Acceptance: `pip install -r requirements-dev.txt && pytest` runs the suite on a clean checkout with no ad-hoc installs.
- Effort: S · Risk: Low

### A3. Document the macOS Celery + ingest→embed gotchas (partly done)
- Finding: §6 prefork crash `[VERIFIED]`; §3 ingest→embed decoupling `[VERIFIED]`. Already partially captured in `CLAUDE.md` this session.
- Files: `CLAUDE.md` (verify present), `run.py` / `dev` (default `--pool=solo` on macOS).
- Approach: make `run.py`/`./dev` select `--pool=solo` on Darwin (or set `OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES` + a fork-safe pool); confirm the CLAUDE.md notes.
- Acceptance: `./dev up` on macOS ingests a PDF to completion without a worker crash, with no manual flag.
- Effort: S · Risk: Low

### A4. Add lint/type gates locally (wiring only; enforcement is B3)
- Finding: §8 no lockfile/SCA; §4 L-4 deprecations.
- Files: `requirements-dev.txt` (mypy), `frontend` (already has eslint/tsc).
- Approach: get `mypy app main.py` and `tsc --noEmit` runnable locally and triage (don't fix-all yet); fix the `datetime.utcnow()` deprecations (L-4) as the first easy win.
- Acceptance: `mypy` and `tsc --noEmit` run and produce a baseline report; `datetime.utcnow()` warnings gone from the pytest run.
- Effort: M · Risk: Low

---

## WS-B — Safety rails / integration CI  *(Audit Phase 1 · THE GATE · highest leverage)*

### B1. Stand up ephemeral infra in CI
- Finding: `H-2` `[VERIFIED]`.
- Files: `.github/workflows/ci.yml` (service containers for Postgres + Milvus + MinIO + Redis, or testcontainers).
- Approach: add a CI job that boots the four data services (Milvus needs etcd+minio-milvus — reuse `docker-compose.yml` via `docker compose up -d` in CI), runs migrations + setup scripts.
- Acceptance: CI job reaches `/health?check_services=true` = all healthy before tests run.
- Effort: M · Risk: Low · Depends: A1, A2

### B2. Run the security-critical integration suites in CI
- Finding: `H-2`, §7 (canary/e2e never run) `[VERIFIED inventory]`.
- Files: `ci.yml`; possibly `conftest.py` (a CI marker).
- Approach: new CI step `RUN_INTEGRATION_TESTS=1 pytest tests/test_acl_canary.py tests/test_acl_e2e.py tests/test_ingestion_e2e.py` against B1 infra. **Confirm-first:** these are `[INFERRED — not executed this pass]`; run them once locally, fix any that are stale, then wire to CI.
- Acceptance: those three suites pass in CI on PRs and are **required checks** (branch protection).
- Effort: M · Risk: Med (suites may need fixes) · Depends: B1

### B3. Add frontend tests + typecheck + backend mypy to CI
- Finding: `H-2`, §7 (`vitest` exists, never runs), §8 (no typecheck).
- Files: `ci.yml`.
- Approach: add `npm run test` + `tsc --noEmit` to the frontend job; add `mypy` (non-blocking baseline first, then blocking) to the backend job.
- Acceptance: `evidence.test.ts` runs in CI; `tsc --noEmit` is a required check; mypy baseline recorded.
- Effort: S · Risk: Low · Depends: A4

### B4. Add dependency/secret scanning
- Finding: §5 (no SCA) `[ASSUMED — not run]`.
- Files: `ci.yml` (`pip-audit`, `npm audit --audit-level=high`), Dependabot config.
- Approach: add SCA steps (non-blocking first), enable Dependabot.
- Acceptance: CI surfaces known CVEs; Dependabot PRs open for outdated deps.
- Effort: S · Risk: Low

---

## WS-C — Close the perimeter  *(Audit Phase 2 security · waves 1 ship early; refactor waits for WS-B)*

### C1. Fail-closed ACL default  *(Top-10 #3)*
- Finding: `H-1` `[VERIFIED config.py:106]`.
- Files: `backend/app/config.py`, startup in `main.py`.
- Approach: default `acl_enabled=True`; add a startup guard that refuses to boot a prod profile with ACL off (loud error, not a warning).
- Acceptance: app refuses to start in prod profile with `ACL_ENABLED=false`; default config has ACL on.
- Effort: S · Risk: Low · Depends: none (ship early)

### C2. Authenticate write routes; derive tenant from identity  *(Top-10 #1)*
- Finding: `C-1` `[VERIFIED ingest.py:697-708]`.
- Files: `routes/ingest.py` (`/document`, `/metadata-preview`, `/process`), `acl/dependencies.py`.
- Approach: add `Depends(require_entitlements)` to write routes; ignore the client `tenant_id` form field in favor of `entitlements.tenant_id`; validate `visibility/allowed_*` against the caller's tenant.
- Acceptance: unauthenticated `POST /v1/ingest/document` → 401; a form-supplied `tenant_id` is overridden by identity (integration test).
- Effort: M · Risk: Med · Depends: B2 (so we can prove no isolation regression)

### C3. Verify identity from signed tokens (replace header-trust)  *(Top-10 #2 · epic)*
- Finding: `C-2` `[VERIFIED resolver.py:18-39]`. **This is an epic — split:**
  - C3a. Decide the model (JWT/OIDC vs hardened reverse-proxy with mTLS/shared-secret). *(design, see Open Question 1)*
  - C3b. Add token validation middleware; derive `Entitlements` from verified claims.
  - C3c. Reject the trusted `X-*` headers unless they arrive from an authenticated proxy hop.
- Files: `acl/resolver.py`, new auth middleware, `main.py`.
- Acceptance: a request with forged `X-Roles: admin` and no valid token is denied admin scope (integration test); direct `:8000` access cannot assert identity.
- Effort: L · Risk: Med · Depends: B2, C2, Open Question 1

### C4. Canonicalize `file://` reads  *(Top-10 partial)*
- Finding: `H-8` `[VERIFIED code; INFERRED exploitability]`.
- Files: `routes/documents.py:705-708`.
- Approach: `os.path.realpath` + allow-list root prefix; reject `..`/non-allowed paths. **Confirm-first:** check whether any normal flow produces `file://` source_uris.
- Acceptance: a doc with `source_uri="file:///etc/passwd"` returns 403; legitimate allow-listed paths still load.
- Effort: S · Risk: Low

### C5. Harden secret defaults & CORS  *(M-1, L-1)*
- Finding: `M-1` `[VERIFIED]`, `L-1` `[VERIFIED]`.
- Files: `config.py` (empty defaults for `db_password`/`minio_*`, fail-fast in prod), `main.py` (restrict CORS methods/headers).
- Approach: empty-string secret defaults + a prod-profile validation that fails on unset/default creds; narrow CORS `allow_methods`/`allow_headers` to what's used.
- Acceptance: prod profile refuses to boot with default `ragpass`/`minioadmin`; CORS no longer wildcards methods/headers.
- Effort: S · Risk: Low

### C6. Reduce PII in logs  *(M-2)*
- Finding: `M-2` `[INFERRED runner.py:626-633]`. Confirm-first.
- Files: `qa/runner.py`.
- Approach: move question-text logs to DEBUG; at INFO log length/hash + tenant id only.
- Acceptance: at INFO level, no raw question text appears in logs (grep a sample run).
- Effort: S · Risk: Low

---

## WS-D — Reliability seams  *(Audit Phase 2 reliability)*

### D1. Validate citations against retrieved context  *(Top-10 #5)*
- Finding: `H-4` `[VERIFIED runner.py:1216,1305-1462]`.
- Files: `qa/runner.py` (post-extraction), `llm/openai_client.py:375-423`.
- Approach: after extraction, drop or hard-flag any citation whose `node_id ∉ context_node_ids`; emit a dropped-citation counter.
- Acceptance: unit test — a response citing a node_id not in context returns 0 such citations; dropped-count metric present.
- Effort: S · Risk: Low · Depends: characterization test on QA output

### D2. Retry/backoff on OpenAI calls  *(Top-10 #6)*
- Finding: `H-3` `[VERIFIED openai_client.py:245-247, runner.py:303]`.
- Files: `llm/openai_client.py`, `qa/runner.py` (reranker path).
- Approach: bounded exponential backoff (≤3 tries) around answer + rerank calls; categorize 429/timeout/5xx in logs.
- Acceptance: injected 429-then-success yields an answer within ≤3 attempts (unit test with a mocked client).
- Effort: S · Risk: Low

### D3. Job heartbeat + stale-job sweeper  *(Top-10 #7)*
- Finding: `H-6` `[INFERRED tasks/ingest.py:79-147; partially observed live]`. Confirm-first.
- Files: `db/models.py` (`last_heartbeat_at`), `tasks/*`, `routes/ingest.py`, a periodic sweeper.
- Approach: workers update a heartbeat; a sweeper marks jobs `failed` when heartbeat is stale; surface elapsed/last-update in the job API.
- Acceptance: a task killed mid-job transitions to `failed` within the heartbeat window (not stuck `processing`).
- Effort: M · Risk: Med

### D4. Embedding reconciliation + status  *(Top-10 #8 · epic)*
- Finding: `H-5` `[INFERRED pipeline.py:382, embed_nodes.py:351-384]`. Confirm-first.
- Files: `db/models.py` (`embedding_status`), `tasks/embed_nodes.py`, sweeper, `routes/embed.py`.
- Approach: track per-doc embedding status; a reconciliation job finds nodes lacking vectors and re-enqueues; optionally auto-enqueue embed after ingest (resolves the two-step surprise).
- Acceptance: query finds nodes without vectors; sweeper re-embeds; doc reports `embedding_status=complete`; a fresh ingest becomes queryable without a manual embed call.
- Effort: M · Risk: Med · Depends: B2 (ingestion e2e in CI)

### D5. Frontend resilience: fetch timeouts, polling circuit-breaker, terminal states  *(Top-10 #10)*
- Finding: `M-8`, `M-9`, `M-10` `[INFERRED api.ts:605, health-indicator.tsx:40, processing/page.tsx]`.
- Files: `frontend/src/lib/api.ts`, `health-indicator.tsx`, `processing/page.tsx`, a shared fetch wrapper.
- Approach: `AbortController` 30s timeout wrapper; stop polling after N consecutive failures; add `skipped_alias` as a terminal state in `pollIngestJob`; a `formatAPIError` util.
- Acceptance: a stalled request aborts at 30s; poller stops after N failures with a user message; an alias ingest ends polling.
- Effort: M · Risk: Low · Depends: B3 (frontend tests in CI)

---

## WS-E — Modernize  *(Audit Phase 3 · all depend on WS-B green)*

### E1. Centralize ACL enforcement
- Finding: §5 / `L` (scattered enforcement, bypass-on-new-path risk) `[VERIFIED enforcement points; INFERRED bypass risk]`.
- Files: `qa/runner.py` (the 5 enforcement points), `acl/enforcer.py`.
- Approach: wrap all retrieval paths in one ACL-guarded search method so a new path cannot skip enforcement.
- Acceptance: ACL canary suite green after refactor; a deliberately-added unguarded path fails a test.
- Effort: M · Risk: Med · **Depends: B2 (canary in CI) — do not start before**

### E2. Decompose `QARunner` (2847 lines)
- Finding: `L-2` `[VERIFIED file length]`.
- Files: `qa/runner.py` → extract `CitationHydrator`, `Reranker`, `PropagationSafetyRunner`.
- Approach: characterization tests on QA output first, then extract by composition; no behavior change.
- Acceptance: `runner.py` materially smaller; QA output identical on a fixture set; unit tests per extracted component.
- Effort: L · Risk: Med · **Depends: B2, D1**

### E3. Batch/cache figure OCR + spend cap  *(Top-10 #9)*
- Finding: `H-7` `[INFERRED; latency observed live]`. Confirm-first with a cost trace.
- Files: `graph/nodes.py:302`, `ocr/openai_client.py`.
- Approach: bounded-concurrency OCR, cache by figure hash, optional OCR, per-doc spend cap + logging.
- Acceptance: a 270-page doc ingests with bounded-concurrency OCR; per-doc OCR spend capped and logged.
- Effort: L · Risk: Med

### E4. Ops hardening: Redis-backed monitor state + correlation IDs
- Finding: `M-6`, `M-7` `[INFERRED]`.
- Files: `app/monitor/state.py` (Redis), request-id middleware + Celery task context.
- Approach: move monitor state to Redis; inject a request id and propagate through to tasks/logs.
- Acceptance: two workers share monitor state; a request id appears in API + worker logs for one trace.
- Effort: M · Risk: Low

### E5. Dependency hygiene
- Finding: §8 (`jsonschema` unpinned, no Python lock, unused opensearch/neo4j).
- Files: `requirements.txt`, lock tooling.
- Approach: pin `jsonschema`; adopt `pip-tools` lock; decide keep/remove OpenSearch+Neo4j (Open Question 4).
- Acceptance: `requirements.lock` committed; `pip-audit` clean or triaged; unused backends removed or covered by a connection test.
- Effort: M · Risk: Low

---

## Execution Sequence (recommended waves)

**Wave 0 — Foundation (parallelizable, ~days):** A1, A2, A3, A4, C1, C5 — toolchain pinned, fail-closed default, secret/CORS hardening. All low-risk, no cross-deps.

**Wave 1 — The gate (~1–2 weeks):** B1 → B2, B3, B4. Stand up integration CI and make the ACL/ingestion suites required. *Nothing structural proceeds until B2 is green.*

**Wave 2 — Perimeter + cheap reliability (~1–2 weeks):** C2, C4, C6, D1, D2. Auth on writes, `file://` fix, citation validation, LLM retry. (C3 design — Open Question 1 — starts here in parallel.)

**Wave 3 — Reliability seams (~2 weeks):** C3 (token identity, epic), D3, D4, D5.

**Wave 4 — Modernize (ongoing, gated on Wave 1):** E1, E2, E3, E4, E5.

## Tracking table

| ID | Title | Finding | Effort | Risk | Depends on |
|---|---|---|---|---|---|
| A1 | Pin toolchain | §8 | S | Low | — |
| A2 | Declare test toolchain | §8 | S | Low | — |
| A3 | macOS solo + ingest/embed docs | §6/§3 | S | Low | — |
| A4 | Lint/type gates + utcnow fix | §8/L-4 | M | Low | — |
| B1 | Ephemeral infra in CI | H-2 | M | Low | A1,A2 |
| B2 | ACL/ingestion suites in CI (required) | H-2 | M | Med | B1 |
| B3 | Frontend test + typecheck + mypy in CI | H-2 | S | Low | A4 |
| B4 | Dependency/secret scanning | §5 | S | Low | — |
| C1 | Fail-closed ACL default | H-1 | S | Low | — |
| C2 | Auth write routes; tenant from identity | C-1 | M | Med | B2 |
| C3 | Token-verified identity (epic) | C-2 | L | Med | B2,C2,OQ1 |
| C4 | Canonicalize file:// reads | H-8 | S | Low | — |
| C5 | Secret defaults + CORS | M-1,L-1 | S | Low | — |
| C6 | Reduce PII in logs | M-2 | S | Low | — |
| D1 | Validate citations vs context | H-4 | S | Low | char. test |
| D2 | OpenAI retry/backoff | H-3 | S | Low | — |
| D3 | Job heartbeat + sweeper | H-6 | M | Med | — |
| D4 | Embedding reconciliation (epic) | H-5 | M | Med | B2 |
| D5 | Frontend resilience | M-8/9/10 | M | Low | B3 |
| E1 | Centralize ACL enforcement | §5 | M | Med | B2 |
| E2 | Decompose QARunner | L-2 | L | Med | B2,D1 |
| E3 | Batch/cache OCR + cap | H-7 | L | Med | — |
| E4 | Redis monitor state + correlation IDs | M-6,M-7 | M | Low | — |
| E5 | Dependency hygiene | §8 | M | Low | OQ4 |

## Open questions blocking specific tasks
1. **Identity model (blocks C3):** JWT/OIDC at the app, or a hardened reverse proxy with mTLS? Drives the whole auth epic.
2. **Single- vs multi-tenant in production:** if single-tenant, C3/E1 shrink dramatically and H-1 is lower urgency.
3. **OCR necessity (scopes E3):** required for target docs or opt-in?
4. **OpenSearch/Neo4j (blocks E5):** live backends or dead code to remove?

---
*This plan is the source of truth. If you want it mirrored into GitHub issues/milestones (Phase 0–3) or Asana/Notion, say so and I'll generate them from this file.*

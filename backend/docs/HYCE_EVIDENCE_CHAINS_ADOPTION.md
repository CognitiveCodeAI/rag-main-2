# Query-Aware Evidence Chains Adoption Plan

Status: Phase 1 implemented and fully repository-verified behind a default-off feature flag; the locked synthetic and configured-model A/B gates pass, while a representative production pilot and domain review remain required for default-on rollout

Owner: QA/Retrieval

Safety boundary: evidence-chain scores rank evidence; they never verify a claim or a source location.

## 1. Objective

Adopt the useful parts of HyCE-RAG in NPR-RAG so multi-hop questions receive a coherent, auditable chain of source evidence while retaining NPR's exact document provenance, ACL enforcement, and fail-closed highlighting.

The adopted design must:

1. Improve multi-hop retrieval and context assembly without regressing single-hop answers.
2. Preserve an immutable path from every answer citation to the original node, document version, source hash, page, exact quote, and verified locator.
3. Never equate graph relevance, extraction confidence, or propagation score with factual truth.
4. Filter inaccessible nodes before graph traversal, scoring, packing, generation, and citation hydration.
5. Remain feature-gated, observable, reversible, and measurable against the current pipeline.

## 2. Non-goals

- Do not expose private model chain-of-thought. The UI may show only evidence topology, source excerpts, and auditable scores.
- Do not classify a low-scoring path as a contradiction. Contradictions require a separately validated semantic comparison.
- Do not allow approximate source locations to appear verified.
- Do not replace vector retrieval, the propagation-safety verifier, or Evidence Highlighting V2.
- Do not apply expensive graph reasoning to every question.

## 3. Target architecture

```text
question
  -> normalization / constraints / vector retrieval / ACL filter
  -> seed ranking
  -> multi-hop routing gate
       off/single-hop -> current graph expansion and flat packing
       multi-hop      -> authorized neighborhood expansion
                      -> personalized structural propagation
                      -> evidence-chain assembly and deduplication
                      -> chain-aware context packing
  -> answer generation or propagation-safety verification
  -> citation hydration
  -> EvidenceRecord V2 verification
  -> original-document highlight
```

Evidence chains contain node IDs and graph edges only. Evidence verification remains the responsibility of `EvidenceRecord` and the highlighting service.

## 4. Delivery phases

### Phase 0 — baseline and contracts

- Freeze representative standard, legal, clinical, multi-hop, ACL, and highlighting fixtures.
- Record baseline answer correctness, evidence recall, citation precision, verified-highlight rate, p50/p95 latency, context size, and fallback rate.
- Add a benchmark-contract mode whose dataset and SHA-256 are locked.

Exit: repeatable baseline report and all existing tests green.

### Phase 1 — query-aware chains over the existing document graph

- Add deterministic multi-hop routing with `off`, `auto`, and `on` modes.
- Expand only an ACL-authorized neighborhood, with hop and node caps.
- Compute a personalized propagation score from seed relevance, query relevance, and typed edge confidence.
- Assemble paths back to seed evidence, deduplicate overlapping paths, and select within an evidence budget.
- Pack chain nodes in evidence order while keeping canonical `[node_id:page]` markers.
- Add structured audit output: route decision, weights/version, selected nodes, paths, edges, scores, timing, and fallback reason.
- Fall back to the unchanged baseline path on any chain-layer error.

Exit: unit/integration/security gates pass and multi-hop A/B meets release thresholds.

### Phase 2 — semantic entity and hyperedge index

- Introduce versioned `Entity`, `EvidenceHyperedge`, and `HyperedgeIncidence` records. A hyperedge must reference one or more immutable source nodes.
- Extract typed entities and n-ary relations with versioned prompts and schemas.
- Canonicalize aliases within tenant scope. Preserve the original mention and never silently merge below the merge threshold.
- Store entity embeddings in a separately versioned Milvus collection.
- Assemble a request-scoped hypergraph only after document and node ACL filtering.
- Blend document-graph and semantic-hypergraph paths; retain the Phase 1 fallback.
- Add reindex, rollback, backfill, and deletion propagation.

Exit: measured improvement beyond Phase 1, acceptable ingestion cost, alias-error gate, deletion/ACL proof, and successful rollback rehearsal.

### Phase 3 — evidence-chain UI and controlled rollout

- Add an optional "Why this answer?" panel showing claim -> evidence nodes -> source pages.
- Each leaf opens the original document at its independently verified highlight.
- Label structural score as `relevance`, never `confidence` or `truth`.
- Show unavailable/approximate evidence explicitly and do not render it as verified.
- Roll out internal -> clinical/legal pilot -> percentage ramp -> default auto routing.

Exit: usability review with domain users, production telemetry within thresholds, and incident/rollback runbook approved.

## 5. Phase 1 scoring contract

The implementation is deterministic and versioned. It uses:

- a personalized restart distribution derived from normalized seed scores;
- degree-normalized propagation over typed, confidence-weighted edges;
- lexical query relevance as a bounded signal;
- a seed-preservation term;
- explicit hop, node, chain, and context budgets.

All component scores are in `[0, 1]`. Final ordering has stable node-ID tie breaking. Missing or invalid edge confidence is clamped, not trusted. Scores are ranking evidence only.

## 6. Security and provenance invariants

1. The candidate node set is ACL-filtered before any edge is eligible.
2. An edge is eligible only when both endpoints are in the authorized candidate set.
3. Audit output must not include denied node IDs, document IDs, text, aliases, degree counts, or inferred relationships.
4. Cross-tenant entity canonicalization and propagation are prohibited.
5. Packed context contains only authorized nodes.
6. Citations remain restricted to packed node IDs and are ACL-filtered again.
7. Chain metadata cannot set `EvidenceRecord.status` or verification grades.
8. Document/version/source-hash mismatches continue to fail closed.
9. Deletion of a document removes or invalidates all dependent semantic incidences before the next query can use them.

## 7. Test strategy

### Unit

- router true/false positives and deterministic decisions;
- score normalization, convergence, stable ordering, disconnected nodes, cycles, self-loops, invalid confidences, and empty graphs;
- hop/node/context caps and deduplication;
- chain reconstruction and seed preservation;
- serialization and backwards-compatible API defaults;
- fail-open prevention and baseline fallback on exceptions.

### Integration

- vector seeds -> expansion -> chain scoring -> packing -> citation hydration;
- standard and propagation-safety modes;
- exact citation marker preservation;
- current highlighting verification with chain-selected evidence;
- feature off returns the baseline ordering and response contract;
- migration/backfill/idempotency/deletion coverage for Phase 2.

### Security and privacy

- inaccessible neighbors never affect scores or appear in audits;
- mixed-tenant and node-override fixtures;
- cache keys, if introduced, include tenant, entitlements hash, policy version, index version, and scoring version;
- malicious node text cannot alter routing/scoring configuration;
- restricted entity aliases and graph degree are not leaked.

### Evaluation

- locked legal cases: clause + amendment + effective date + governing authority;
- locked clinical cases: condition + treatment + contraindication + current guideline;
- supersession, temporal conflict, aliases, abbreviation ambiguity, same-name entities, hub distractors, missing hops, and unsupported questions;
- standard single-hop and vague-question regression set;
- human-reviewed expected nodes/pages/quotes, not LLM judgment alone.

### Performance and resilience

- p50/p95/p99 chain-layer latency and total request latency;
- maximum SQL query count and candidate count;
- propagation convergence and memory under worst-case bounded graphs;
- database timeout/error fallback;
- load test with feature off, auto-routed, and forced-on cohorts;
- rollback rehearsal with no response-schema or citation breakage.

## 8. Release gates

Phase 1 may move from shadow evaluation to user-visible auto routing only when all gates pass:

| Gate | Required result |
|---|---|
| Multi-hop answer correctness | at least +5 absolute points over baseline |
| Complete evidence-chain recall | no regression; target +5 absolute points |
| Citation precision | no regression |
| Verified-highlight rate | no regression |
| Wrong document/page/version verified | exactly 0 |
| Unauthorized evidence/audit leakage | exactly 0 |
| Single-hop correctness | no statistically meaningful regression |
| Chain-layer p95 overhead | <= 20% of baseline total latency |
| Fallback/degeneracy rate | <= 10% |
| Unsupported-answer rate | no regression |

Phase 2 additionally requires entity merge precision, extraction recall, deletion correctness, reindex reproducibility, and ingestion cost gates.

## 9. Observability and rollback

Emit per-request structured fields without source text:

- scoring version and mode;
- router decision and reason codes;
- candidate/edge/path counts;
- selected node IDs only after ACL filtering;
- convergence iterations and timing;
- fallback status/reason;
- context tokens and downstream verified/approximate/unavailable counts.

Rollback mechanisms:

1. Set evidence-chain feature flag off for immediate baseline behavior.
2. Keep old API fields optional during rollback.
3. Retain independent index versions and an active-index pointer for Phase 2.
4. Preserve baseline evaluation artifacts for every release candidate.

## 10. Completion evidence

Adoption is complete only when:

- implementation, API contract, configuration, and operator documentation are present;
- locked tests and benchmark fixtures cover every invariant above;
- targeted and complete backend/frontend suites pass;
- live or representative-stack integration, performance, ACL, and highlighting tests pass;
- the A/B release report satisfies every applicable gate;
- rollout and rollback are rehearsed and documented.

## 11. Operator rollout and rollback runbook

The global feature flag is the authority boundary. A request-level
`evidence_chain_mode` override is ignored while the global flag is disabled.

### Stage A — baseline/default

```dotenv
EVIDENCE_CHAIN_ENABLED=false
EVIDENCE_CHAIN_MODE=auto
```

This preserves the original expansion and packing path. The optional response
fields remain backwards compatible.

### Stage B — internal forced-on validation

```dotenv
EVIDENCE_CHAIN_ENABLED=true
EVIDENCE_CHAIN_MODE=on
```

Use a non-production corpus first. Confirm that every cited leaf opens the
correct document version and that no unresolved/approximate location is shown
as verified. An API caller may send `evidence_chain_mode: "off"` to obtain a
same-build baseline comparison.

### Stage C — legal/clinical pilot

```dotenv
EVIDENCE_CHAIN_ENABLED=true
EVIDENCE_CHAIN_MODE=auto
```

Run baseline and auto-routed cohorts on the locked representative corpus.
Review node/page/quote expectations with domain reviewers and calculate every
gate in section 8. Do not promote on retrieval recall alone.

### Immediate rollback

Set `EVIDENCE_CHAIN_ENABLED=false` and restart the backend deployment. No data
migration or index rollback is needed for Phase 1. Existing response consumers
continue working because `evidence_chain` is optional.

### Verification commands

From `backend/`:

```bash
python tests/eval/run_evidence_chain_eval.py --output tests/eval/report_evidence_chain.json
python tests/eval/run_evidence_chain_ab.py --output tests/eval/report_evidence_chain_ab_fixture.json
python tests/eval/run_evidence_chain_ab.py --provider openai --model gpt-5.2 --output tests/eval/report_evidence_chain_ab_openai.json
pytest tests/qa/test_evidence_chain.py tests/qa/test_evidence_chain_runner.py -q
RUN_INTEGRATION_TESTS=1 pytest tests/test_evidence_chain_integration.py -q
pytest -q
```

The provider-backed run sends the locked synthetic legal/clinical prompts to
the configured external provider. Obtain the required data-egress approval
before running it. A previously saved report can be checked against the current
locked dataset, expectations, metrics, and gates without another provider call:

```bash
python tests/eval/run_evidence_chain_ab.py \
  --regrade tests/eval/report_evidence_chain_ab_openai.json \
  --output tests/eval/report_evidence_chain_ab_openai.json
```

From `frontend/`:

```bash
npm test
npm run lint
npm run build
```

The locked evaluator covers 12 curated legal, clinical, ACL, single-hop, and
unsupported-answer cases. It validates answers, exact expected facts and
limitations, selected evidence, citations, source locations, ACL leakage,
routing, fallback, and latency. It is deliberately not a substitute for an
ingested, embedded, access-controlled production-like corpus or review by
lawyers and clinicians. Preserve baseline and chain reports for every pilot.

The chain-layer p95 release gate and total request latency are separate. The
chain layer must remain at or below 20% of baseline request p95. Provider/model
request p50/p95/p99 and paired overhead are also reported, but no default-on
decision may rely on the small curated sample; representative load testing is
required.

## 12. Phase 1 implementation map

| Concern | Implementation |
|---|---|
| Routing, propagation, path assembly | `app/qa/evidence_chain.py` |
| Standard and propagation-safety orchestration | `app/qa/runner.py` |
| Bounded chain-aware packing | `app/graph/context_packer.py` |
| Feature configuration | `app/config.py`, `.env.example` |
| API request/response contract | `app/routes/qa.py`, `frontend/src/lib/api.ts` |
| Source-review UI | `frontend/src/app/(app)/chat/chat-client.tsx` |
| Citation contract validation and bounded repair | `app/llm/openai_client.py`, `app/prompts/qa_answer_v2.txt` |
| Locked retrieval evaluator and fixtures | `tests/eval/run_evidence_chain_eval.py`, `tests/eval/questions_evidence_chain.json` |
| Paired answer/provenance A/B | `tests/eval/run_evidence_chain_ab.py`, `tests/eval/evidence_chain_ab_expectations.json` |
| PostgreSQL/ACL/highlighting proof | `tests/test_evidence_chain_integration.py` |

Phase 2 is intentionally not included in the current runtime. Semantic entity
canonicalization and hyperedges have materially higher privacy and merge-error
risk and must earn adoption through a measured improvement beyond Phase 1.

## 13. Phase 1 completion and rollout boundary

The repository implementation is complete for Phase 1. The locked retrieval
report, deterministic paired A/B, configured OpenAI `gpt-5.2` paired A/B,
PostgreSQL integration, migrations, complete backend/frontend suites, and real
browser PDF overlay all pass. The traversal query contract is bounded to at
most two ORM queries per configured hop, in addition to independently enforced
ACL work, and is protected by a regression test.

This does **not** authorize a production default-on change. The configured-model
run is a 12-case curated synthetic evaluation, not a statistically powered
legal or clinical study. Its chain computation added less than 1 ms at p95,
but total model request p95 was 31.29% higher than baseline in that run. Longer,
more complete answers and provider variance can both contribute. Run a
representative load test and have domain reviewers validate answer utility and
every highlighted source before moving beyond a controlled pilot.

## 14. Paper-to-system traceability and intentional deviations

Source: [HyCE-RAG, arXiv:2607.22597v1](https://arxiv.org/abs/2607.22597)

| Paper mechanism | NPR-RAG decision |
|---|---|
| Query-aware neighborhood from retrieved entries | Adopted now, using authorized chunk seeds and the existing document graph |
| Random-walk propagation with restart | Adopted now with deterministic, degree-normalized, bounded propagation |
| Joint structural, query, entry, and reliability scoring | Adopted in available form: propagation, lexical query relevance, seed prior, typed edge weight/confidence |
| Evidence budget and overlap fusion | Adopted now with node/path caps and Jaccard-style path deduplication |
| Structured evidence before generation | Adopted now while preserving canonical citation markers |
| Entity extraction plus entity-vector entry retrieval | Deferred to Phase 2 pending extraction and linking evaluation |
| N-ary hyperedges and incidence traversal | Deferred to Phase 2 pending schema, ACL, deletion, reindex, and provenance proof |
| Lower-score paths treated as potentially contradictory | Not adopted; low relevance is not proof of contradiction |
| `confidence` exposed as evidence quality | Renamed/reframed as structural `relevance`; it cannot verify truth or location |

The paper reports strong benchmark improvements, including on a medical subset,
but its accuracy/relevance/faithfulness measures substantially use an LLM judge.
It does not establish legal-domain performance, exact original-document
highlight correctness, tenant/node ACL safety, entity-merge precision, deletion
behavior, or production latency. NPR-RAG therefore treats the paper as a useful
design hypothesis and requires its own human-reviewed evidence, source-location,
security, and live A/B gates before enabling the feature by default.

# Evidence Chains Phase 1 Verification Record

Date: 2026-08-01

Scope: HyCE-inspired query-aware evidence chains plus the existing Evidence
Highlighting V2 safety boundary.

## Verified outcomes

| Verification | Result |
|---|---|
| Complete default backend suite | 384 passed, 135 intentionally skipped |
| Final evidence-chain/A-B targeted regression | 19 passed |
| Route and PostgreSQL integration selection | 45 passed |
| Generated-PDF ingestion -> graph -> chain integration | passed |
| Authorized chain -> packing -> exact rectangles | passed |
| Wrong-page highlight request | failed closed as `page_not_indexed` |
| Locked retrieval evaluator | 12/12 cases passed |
| Deterministic paired answer/provenance A/B | all gates passed |
| Configured OpenAI `gpt-5.2` paired A/B | all curated gates passed |
| Frontend component tests | 12 passed in 3 files |
| ESLint | 0 errors; 30 pre-existing warnings |
| Next.js production build and TypeScript | passed; 16 static pages generated |
| Browser evidence path -> original PDF -> verified overlay | passed; 0 browser warnings |
| Alembic clean upgrade and 014 downgrade/upgrade rehearsal | passed |

## Locked retrieval evaluator metrics

Dataset SHA-256:
`607ec987d8b032858a48fc03c7ca87d1c8db498e46c3a5d8621610e34bc7c7b7`

| Metric | Result |
|---|---|
| Cases | 12 |
| Router accuracy | 100% |
| Baseline evidence recall | 56.94% |
| Chain evidence recall | 100% |
| Absolute evidence-recall change | +43.06 points |
| Forbidden-node leaks | 0 |
| Deterministic repeat rate | 100% |
| Local chain-layer p95 | 0.26 ms in the final run environment |

This is a deterministic retrieval fixture result. It is not evidence of a
43-point answer-accuracy improvement and must not be represented that way.

## Paired answer and provenance A/B

The answer-level evaluator runs the same question and allowed context through a
baseline and chain variant. Expectations are human-authored in the repository;
the evaluator does not use an LLM judge. It checks required facts and
limitations, citation precision/recall, selected evidence recall, citation
integrity, independently verified source spans, wrong document/page/version
negative controls, ACL leakage, routing, fallback, single-hop behavior, safe
unsupported answers, and latency.

Expectations SHA-256:
`5228ebe3c22f4f262e042ca580bd1b2f62256e0e8e406646f9b2f384eb3b9ee5`

| Configured-model metric | Baseline | Chain |
|---|---:|---:|
| All-case answer accuracy | 41.67% | 100% |
| Routed-case answer accuracy | 12.5% | 100% |
| Citation precision | 100% | 100% |
| Expected citation recall | 58.33% | 97.22% |
| Selected evidence recall | 61.11% | 100% |
| Verified highlight rate | 100% | 100% |
| Single-hop accuracy | 100% | 100% |
| Unsupported-answer safe rate | 100% | 100% |

Additional configured-model results: router accuracy 100%, fallback 0%, wrong
locator acceptances 0, unauthorized evidence leaks 0, and inline citation
integrity 100%. These values are for the locked 12-case synthetic corpus and
must not be generalized to production legal or clinical accuracy.

The chain computation itself measured 0.73 ms p50, 0.94 ms p95, and 1.27 ms
p99. That p95 is 0.043% of baseline total request p95 and passes the <=20%
chain-layer gate. Total provider request p95 increased from 2200.39 ms to
2888.94 ms (+31.29%); paired total-request overhead was +34.21% at p50 and
+50.47% at p95. Total provider latency is observational in this small run, not
a release gate, and requires representative load testing before default-on.

The saved configured-model responses were regraded offline after citation-recall
and latency reporting semantics were finalized. Offline regrading verifies the
locked dataset and expectation hashes and makes no provider call.

## Representative-stack proof

The integration suite creates a real three-page PDF in memory, runs native PDF
extraction, page-bounded chunking, word provenance, selector construction,
PostgreSQL node/edge persistence, ACL-filtered evidence propagation, and path
assembly. A second case inserts a node-level restricted neighbor and proves that
the denied node appears in neither selection, audit, packed context, nor path.
The authorized leaf resolves to verified source rectangles; a wrong-page lookup
is unavailable rather than approximately highlighted.

The repository's older `tests/test_graph_e2e.py` was also invoked explicitly,
but its checked-in test expects `tests/docs/2404.08865v1.pdf`, which is absent
from this worktree. That fixture defect is independent of this implementation;
the generated-PDF integration above supplies the equivalent relevant coverage
without weakening or silently altering the old test.

## Browser proof

The browser fixture verified that:

- the panel labels path scores as relevance and disclaims truth/medical/legal confidence;
- supporting context not cited in the final answer is disabled;
- a cited leaf marked verified opens the existing document viewer;
- the original PDF renders at the cited page with a normalized orange evidence
  rectangle over the source text;
- the panel and nested viewer produce no accessibility warnings.

Screenshot: `output/playwright/evidence-chain-source-panel.png`

## Default-on gates still requiring representative production data

The feature remains disabled by default. These gates cannot be established by
synthetic fixtures or a local build and remain prerequisites for production
default-on rollout:

- human-reviewed answer utility, citation precision, and verified-highlight
  correctness on real legal and clinical documents;
- single-hop and unsupported-answer non-regression with representative traffic;
- total request latency and throughput under representative concurrency;
- fallback/degeneracy rate under live query distribution;
- domain reviewer usability acceptance.

See `HYCE_EVIDENCE_CHAINS_ADOPTION.md` for thresholds, staged rollout, and the
one-flag rollback procedure.

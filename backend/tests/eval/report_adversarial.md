# QA Evaluation Report

**Document:** tests/docs/2404.08865v1.pdf
**Doc ID:** `93e7889b428b7579d8221db3b57a93b6`
**Timestamp:** 2026-01-14T22:47:30.522736
**Total Time:** 7052ms

## Summary

| Metric | Value |
|--------|-------|
| Questions | 2 |
| Successful | 2 |
| Evidence Recall | 2/2 (100%) |
| Keyword Match Avg | 0.0% |

## Results by Question

| # | Question | Seeds | Expanded | Evidence | Keywords | Figures | Intent | Time |
|---|----------|-------|----------|----------|----------|---------|--------|------|
| adv1 | What is the SQuAD accuracy reported... | 5 | 14 | PASS | N/A | N/A | results | 3067ms |
| adv2 | How does this paper compare to the ... | 5 | 16 | PASS | N/A | N/A | results | 3985ms |

## Detailed Results

### adv1: What is the SQuAD accuracy reported in this paper?

**Seeds:** 5 | **Expanded:** 14 | **Edges:** 9 | **Tokens:** 4792

**Query Normalization:**
  - Q0: `What is the SQuAD accuracy reported in this paper?`
  - Q1: `squad the squad reported squad accuracy accuracy`

**Detected Intent:** results

**Seed Pages:** [2, 4, 6, 7]

**Evidence Recall:** PASS ✓
  - Reason: No evidence required

**Answer:**

> I cannot find sufficient information in the provided context. The context does not include any SQuAD accuracy value for the paper (it discusses needle-in-a-haystack recall tests and includes Table 2 and Table 5, but no SQuAD results) [seed:2].

**Citations:** 1
  - seed: page 2

---

### adv2: How does this paper compare to the RAG benchmark results from BEIR or MTEB?

**Seeds:** 5 | **Expanded:** 16 | **Edges:** 11 | **Tokens:** 5184

**Query Normalization:**
  - Q0: `How does this paper compare to the RAG benchmark results from BEIR or MTEB?`
  - Q1: `compare benchmark results beir rag`

**Detected Intent:** results

**Seed Pages:** [1, 4, 6, 12]

**Evidence Recall:** PASS ✓
  - Reason: No evidence required

**Answer:**

> I cannot find sufficient information in the provided context to compare this paper’s needle-in-a-haystack recall results to RAG benchmark results from BEIR or MTEB. The provided context discusses needle-in-a-haystack recall testing across nine LLMs (Tables 1, 2, 5) and factors affecting recall (prompt dependence, training-data conflict, parameters, architecture/training strategy, fine-tuning), but it does not report BEIR/MTEB results or any direct comparison to those benchmarks [adjacent:1] [adj...

**Citations:** 4
  - adjacent: page 1
  - adjacent: page 2
  - adjacent: page 5
  - seed: page 4

---

## Query Normalization Summary

| Intent | Questions |
|--------|-----------|
| results | 2 |

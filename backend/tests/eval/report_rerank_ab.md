# Rerank A/B Report

**Document:** tests/docs/2404.08865v1.pdf
**Doc ID:** `93e7889b428b7579d8221db3b57a93b6`
**Timestamp:** 2026-01-29T00:58:56.240301

## Summary

| Metric | Baseline | Rerank |
|--------|----------|--------|
| Evidence Recall | 5/10 | 5/10 |
| Seed Precision@5 (avg) | 0.20 | 0.20 |
| Seed Precision Improved (count) | - | 0 |
| Rerank Degenerate (count) | - | 0 |
| Rerank Delta (avg) | - | 0.0% |
| Latency Overhead (avg) | - | 141ms (1.9%) |

## Results by Question

| # | SeedPrec@5 Base | SeedPrec@5 Rerank | Delta | Latency +ms | Degenerate | Seeds Changed |
|---|------------------|------------------|-------|-------------|------------|---------------|
| q1 | 0.00 | 0.00 | 0.0% | 0 | No | No |
| q2 | 0.20 | 0.20 | 0.0% | -2143 | No | No |
| q3 | 0.00 | 0.00 | 0.0% | 878 | No | No |
| q4 | 0.40 | 0.40 | 0.0% | 1071 | No | No |
| q5 | 0.40 | 0.40 | 0.0% | -2022 | No | No |
| q6 | 0.20 | 0.20 | 0.0% | 53 | No | No |
| q7 | 0.80 | 0.80 | 0.0% | 234 | No | No |
| q8 | 0.00 | 0.00 | 0.0% | 0 | No | No |
| q9 | 0.00 | 0.00 | 0.0% | -214 | No | No |
| q10 | 0.00 | 0.00 | 0.0% | 3549 | No | No |

## Detailed Rankings

### q1: What is the main claim of this paper regarding language model performance?

**Rerank Status:** OK
**Baseline Seeds:** 
**Rerank Seeds:** 
**Rerank Changed Seeds:** No

---

### q2: What is the 'lost in the middle' phenomenon?

**Rerank Status:** OK
**Baseline Seeds:** ec6b65ee090172b89a4db458b67bea71, 6f6d1d25950efb8a806e612b3520c7a2, 7b6f0d703fd7880d71a666f5f92ede50, 8754f822581c370b835bbb52b9e2beb6, 3f22a873314b3524066bfcc9e37c5b14
**Rerank Seeds:** ec6b65ee090172b89a4db458b67bea71, 6f6d1d25950efb8a806e612b3520c7a2, 7b6f0d703fd7880d71a666f5f92ede50, 8754f822581c370b835bbb52b9e2beb6, 3f22a873314b3524066bfcc9e37c5b14
**Rerank Changed Seeds:** No

---

### q3: What models were evaluated in this study and what are their context lengths?

**Rerank Status:** OK
**Baseline Seeds:** 8754f822581c370b835bbb52b9e2beb6, 3efda4789c97dc672425960ce102fb33, 3f22a873314b3524066bfcc9e37c5b14, 4c02b1366b05e085b1ce157abf5e44ec, fa4e7dd03d712a77897e0090a911ed29
**Rerank Seeds:** 8754f822581c370b835bbb52b9e2beb6, 3efda4789c97dc672425960ce102fb33, 3f22a873314b3524066bfcc9e37c5b14, 4c02b1366b05e085b1ce157abf5e44ec, fa4e7dd03d712a77897e0090a911ed29
**Rerank Changed Seeds:** No

---

### q4: What does Figure 1 show about model performance?

**Rerank Status:** OK
**Baseline Seeds:** e8b40650928b74b880511b759106fd5a, b562aab0119815292d5f9fedd2f81133, c04d5f45d6dbe10161a1d49eab4baad3, 626825ef80fc7afdaac9c759c4096efc, f929d0490c09ef436a3a889dc0efaf55
**Rerank Seeds:** e8b40650928b74b880511b759106fd5a, b562aab0119815292d5f9fedd2f81133, c04d5f45d6dbe10161a1d49eab4baad3, 626825ef80fc7afdaac9c759c4096efc, f929d0490c09ef436a3a889dc0efaf55
**Rerank Changed Seeds:** No

---

### q5: How does the position of relevant information affect accuracy in the multi-document QA task?

**Rerank Status:** OK
**Baseline Seeds:** ec6b65ee090172b89a4db458b67bea71, 7b6f0d703fd7880d71a666f5f92ede50, 4c02b1366b05e085b1ce157abf5e44ec, f929d0490c09ef436a3a889dc0efaf55, 626825ef80fc7afdaac9c759c4096efc
**Rerank Seeds:** ec6b65ee090172b89a4db458b67bea71, 7b6f0d703fd7880d71a666f5f92ede50, 4c02b1366b05e085b1ce157abf5e44ec, f929d0490c09ef436a3a889dc0efaf55, 626825ef80fc7afdaac9c759c4096efc
**Rerank Changed Seeds:** No

---

### q6: What datasets were used to evaluate the models?

**Rerank Status:** OK
**Baseline Seeds:** 58818decaf800c3579e754ed168a29c6, 10fd457a45aa25f907aefc29756ba053, f929d0490c09ef436a3a889dc0efaf55, aafccb0807557db11ee83126199a3a69, a78419a816993ed35466eedf5dc9a8de
**Rerank Seeds:** 58818decaf800c3579e754ed168a29c6, 10fd457a45aa25f907aefc29756ba053, f929d0490c09ef436a3a889dc0efaf55, aafccb0807557db11ee83126199a3a69, a78419a816993ed35466eedf5dc9a8de
**Rerank Changed Seeds:** No

---

### q7: According to Table 1 or Table 2, which model performed best overall?

**Rerank Status:** OK
**Baseline Seeds:** 4617ef98776db921f3fe5587fde3a03c, a05507c0446ee171033766536987782d, b562aab0119815292d5f9fedd2f81133, fa4e7dd03d712a77897e0090a911ed29, ec6b65ee090172b89a4db458b67bea71
**Rerank Seeds:** 4617ef98776db921f3fe5587fde3a03c, a05507c0446ee171033766536987782d, b562aab0119815292d5f9fedd2f81133, fa4e7dd03d712a77897e0090a911ed29, ec6b65ee090172b89a4db458b67bea71
**Rerank Changed Seeds:** No

---

### q8: What are the practical implications of this research for RAG systems?

**Rerank Status:** OK
**Baseline Seeds:** 
**Rerank Seeds:** 
**Rerank Changed Seeds:** No

---

### q9: What is the key-value retrieval task and why was it used?

**Rerank Status:** OK
**Baseline Seeds:** 6654dbb6a9c246020962df29d75c3fc3, 4c02b1366b05e085b1ce157abf5e44ec, 58818decaf800c3579e754ed168a29c6, 10fd457a45aa25f907aefc29756ba053, 8754f822581c370b835bbb52b9e2beb6
**Rerank Seeds:** 6654dbb6a9c246020962df29d75c3fc3, 4c02b1366b05e085b1ce157abf5e44ec, 58818decaf800c3579e754ed168a29c6, 10fd457a45aa25f907aefc29756ba053, 8754f822581c370b835bbb52b9e2beb6
**Rerank Changed Seeds:** No

---

### q10: What recommendations do the authors make for future work or system design?

**Rerank Status:** OK
**Baseline Seeds:** fa4e7dd03d712a77897e0090a911ed29, 3d3a6e9aa47b065363075ebdd8c57dcc, 626825ef80fc7afdaac9c759c4096efc, 7b6f0d703fd7880d71a666f5f92ede50, b323f697d068866c11c3a371ab987403
**Rerank Seeds:** fa4e7dd03d712a77897e0090a911ed29, 3d3a6e9aa47b065363075ebdd8c57dcc, 626825ef80fc7afdaac9c759c4096efc, 7b6f0d703fd7880d71a666f5f92ede50, b323f697d068866c11c3a371ab987403
**Rerank Changed Seeds:** No

---

## DIAGNOSTIC: Candidate JSON Sample (q10)

**Purpose:** Debug why `section=None` appears in all rerank candidates.

*No rerank candidates available for diagnostic.*

## Confirmation

- No modules outside the reranking path were modified.
- Ordering stability enforced via deterministic tie-breakers.

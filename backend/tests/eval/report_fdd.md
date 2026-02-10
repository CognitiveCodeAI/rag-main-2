# QA Evaluation Report

**Document:** C:/Apps/rag/2025 FDD.pdf
**Doc ID:** `37660ee55b1fb2aa63579e3aeb2aca97`
**Timestamp:** 2026-01-29T01:28:26.771656
**Total Time:** 85872ms

## Summary

| Metric | Value |
|--------|-------|
| Questions | 20 |
| Successful | 18 |
| Evidence Recall | 16/20 (80%) |
| Keyword Match Avg | 95.6% |

## Results by Question

| # | Question | Seeds | Expanded | Evidence | Keywords | Figures | Intent | Time |
|---|----------|-------|----------|----------|----------|---------|--------|------|
| q1 | What is the initial franchise fee f... | 5 | 10 | PASS | 3/3 | N/A | - | 2935ms |
| q2 | What is the royalty percentage that... | 5 | 14 | PASS | 3/3 | N/A | - | 1940ms |
| q3 | What is the minimum weekly royalty ... | 5 | 12 | PASS | 3/3 | N/A | - | 1745ms |
| q4 | What services does a Ziebart franch... | 5 | 13 | PASS | 4/5 | N/A | - | 8433ms |
| q5 | Who is the Chairman of the Board of... | 5 | 14 | PASS | 2/2 | N/A | - | 2802ms |
| q6 | What is the estimated initial inves... | 5 | 9 | FAIL | 2/2 | N/A | - | 2412ms |
| q7 | What is the Multi-Unit Development ... | 5 | 15 | FAIL | 3/3 | N/A | - | 2583ms |
| q8 | What trademarks does Ziebart own? L... | 5 | 12 | PASS | 5/5 | N/A | - | 3173ms |
| q9 | What happens to the franchise upon ... | 0 | 0 | FAIL | N/A | N/A | - | 0ms |
| q10 | What is the address of Ziebart Corp... | 5 | 12 | PASS | 3/4 | N/A | - | 1571ms |
| q11 | What is the opening inventory cost ... | 5 | 11 | PASS | 3/3 | N/A | - | 1921ms |
| q12 | Are there any special provisions fo... | 5 | 13 | PASS | 3/3 | N/A | - | 9311ms |
| q13 | What is required regarding the warr... | 5 | 15 | PASS | 3/3 | N/A | - | 9380ms |
| q14 | What are the Michigan state-specifi... | 5 | 11 | PASS | 2/3 | N/A | - | 7920ms |
| q15 | Is there any pending litigation dis... | 5 | 13 | PASS | 3/3 | N/A | - | 2157ms |
| q16 | What is the training cancellation f... | 5 | 11 | PASS | 3/3 | N/A | - | 2183ms |
| q17 | Who is the Vice President of Inform... | 5 | 11 | PASS | 3/3 | N/A | - | 1411ms |
| q18 | What is the Rhino Linings relations... | 5 | 14 | PASS | 3/3 | N/A | - | 7309ms |
| q19 | What are the provisions for Washing... | 5 | 10 | PASS | 3/3 | N/A | - | 16686ms |
| q20 | What is the environmental complianc... | 0 | 0 | FAIL | N/A | N/A | - | 0ms |

## Detailed Results

### q1: What is the initial franchise fee for a Ziebart franchise?

**Seeds:** 5 | **Expanded:** 10 | **Edges:** 5 | **Tokens:** 3380

**Query Normalization:**
  - Q0: `What is the initial franchise fee for a Ziebart franchise?`
  - Q1: `fee initial ziebart franchise`

**Seed Pages:** [14, 15, 16, 82]

**Seed Sections:** ['Conclusion']

**Evidence Recall:** PASS ✓
  - Reason: Page 14 found in context

**Keywords:** 3/3 matched

**Answer:**

> The initial franchise fee for a Ziebart® franchise is **$45,000**, paid in a lump sum when you sign the Franchise Agreement, and it is **non-refundable** [seed:14].

**Citations:** 1
  - seed: page 14

**Expanded Nodes:** 10
  - a1c6de92034e334c558e367fcb0f128f | chunk | page=14 | label=None
  - 6fd76dc70d15b4406ba0511b7e479c4c | chunk | page=14 | label=None
  - 0af0d414507af06fc2573b73751c9f24 | chunk | page=15 | label=None
  - 6d1be3dc0274b75509c6a70082b1f5d6 | chunk | page=16 | label=None
  - 8d29a3f3c7100edf447b34479a2ec6e1 | chunk | page=82 | label=None
  - 9c048918b40e9f930c329ade59c8866b | chunk | page=13 | label=None
  - f5dde69ad6d2c1b57293d42772b1b05b | chunk | page=15 | label=None
  - 7df3c3398e958c1a097af6a423dcf94f | chunk | page=16 | label=None
  - 81ae3245f0a5ddce61f04a60f8f40603 | chunk | page=81 | label=None
  - 96b5126cf2df95003987c260647df749 | chunk | page=82 | label=None

**Edge Trace:** 5
  - 0af0d414507af06fc2573b73751c9f24 --adjacent--> 9c048918b40e9f930c329ade59c8866b
  - 0af0d414507af06fc2573b73751c9f24 --adjacent--> f5dde69ad6d2c1b57293d42772b1b05b
  - 0af0d414507af06fc2573b73751c9f24 --adjacent--> 7df3c3398e958c1a097af6a423dcf94f
  - 0af0d414507af06fc2573b73751c9f24 --adjacent--> 81ae3245f0a5ddce61f04a60f8f40603
  - 0af0d414507af06fc2573b73751c9f24 --adjacent--> 96b5126cf2df95003987c260647df749

---

### q2: What is the royalty percentage that franchisees must pay?

**Seeds:** 5 | **Expanded:** 14 | **Edges:** 9 | **Tokens:** 4960

**Query Normalization:**
  - Q0: `What is the royalty percentage that franchisees must pay?`
  - Q1: `percentage pay royalty the royalty franchisees`

**Seed Pages:** [3, 16, 19, 20, 83]

**Seed Sections:** ['Conclusion']

**Evidence Recall:** PASS ✓
  - Reason: Page 16 found in context

**Keywords:** 3/3 matched

**Answer:**

> Franchisees must pay a royalty of **8% of Gross Sales** (with certain listed products/services charged at **5%**) [seed:16] [seed:19].

**Citations:** 2
  - seed: page 16
  - seed: page 19

**Expanded Nodes:** 14
  - 17e6694087eac0440d0dbda4369f4aef | chunk | page=3 | label=None
  - 7df3c3398e958c1a097af6a423dcf94f | chunk | page=16 | label=None
  - 5eebc8f832510c5e221c62c7c33607a4 | chunk | page=19 | label=None
  - 61f9f9818b8a088542c0a840629c7db0 | chunk | page=20 | label=None
  - 7b9b2312a9f8970cf71510670c579828 | chunk | page=83 | label=None
  - e09402bbe54d8fe17cfeda6c62ce67d7 | chunk | page=2 | label=None
  - 63f517d307e5b0b177087f7edc739fbd | chunk | page=4 | label=None
  - c4871760f79359a6eedb36d4297ebe82 | chunk | page=17 | label=None
  - 6d1be3dc0274b75509c6a70082b1f5d6 | chunk | page=16 | label=None
  - 083406ffd30e6804778be302477b3596 | chunk | page=18 | label=None

**Edge Trace:** 9
  - 17e6694087eac0440d0dbda4369f4aef --adjacent--> e09402bbe54d8fe17cfeda6c62ce67d7
  - 17e6694087eac0440d0dbda4369f4aef --adjacent--> 63f517d307e5b0b177087f7edc739fbd
  - 17e6694087eac0440d0dbda4369f4aef --adjacent--> c4871760f79359a6eedb36d4297ebe82
  - 17e6694087eac0440d0dbda4369f4aef --adjacent--> 6d1be3dc0274b75509c6a70082b1f5d6
  - 17e6694087eac0440d0dbda4369f4aef --adjacent--> 083406ffd30e6804778be302477b3596
  - 17e6694087eac0440d0dbda4369f4aef --adjacent--> a2a5b7c099b0fdcf842ab6aa550d4d90
  - 17e6694087eac0440d0dbda4369f4aef --adjacent--> 98fbc94da1e7de410987462e573bf31a
  - 17e6694087eac0440d0dbda4369f4aef --adjacent--> a6dafcadd49b6110f3e3d724bc4859a0
  - 17e6694087eac0440d0dbda4369f4aef --adjacent--> f422abdf2bcbe75e4f43f879a962dbb0

---

### q3: What is the minimum weekly royalty amount?

**Seeds:** 5 | **Expanded:** 12 | **Edges:** 7 | **Tokens:** 3959

**Query Normalization:**
  - Q0: `What is the minimum weekly royalty amount?`
  - Q1: `amount weekly minimum royalty the minimum`

**Seed Pages:** [16, 20, 21, 83, 84]

**Seed Sections:** ['Conclusion']

**Evidence Recall:** PASS ✓
  - Reason: Page 16 found in context

**Keywords:** 3/3 matched

**Answer:**

> The minimum weekly royalty will not be less than **$650.00 per week per location** [seed:20].

**Citations:** 1
  - seed: page 20

**Expanded Nodes:** 12
  - 7df3c3398e958c1a097af6a423dcf94f | chunk | page=16 | label=None
  - 61f9f9818b8a088542c0a840629c7db0 | chunk | page=20 | label=None
  - 13fec372ac78a60df084887c05aead87 | chunk | page=21 | label=None
  - 7b9b2312a9f8970cf71510670c579828 | chunk | page=83 | label=None
  - f422abdf2bcbe75e4f43f879a962dbb0 | chunk | page=84 | label=None
  - c4871760f79359a6eedb36d4297ebe82 | chunk | page=17 | label=None
  - 6d1be3dc0274b75509c6a70082b1f5d6 | chunk | page=16 | label=None
  - a2a5b7c099b0fdcf842ab6aa550d4d90 | chunk | page=19 | label=None
  - 98fbc94da1e7de410987462e573bf31a | chunk | page=20 | label=None
  - 21bb56be795390589bfa354429b20d78 | chunk | page=22 | label=None

**Edge Trace:** 7
  - f422abdf2bcbe75e4f43f879a962dbb0 --adjacent--> c4871760f79359a6eedb36d4297ebe82
  - f422abdf2bcbe75e4f43f879a962dbb0 --adjacent--> 6d1be3dc0274b75509c6a70082b1f5d6
  - f422abdf2bcbe75e4f43f879a962dbb0 --adjacent--> a2a5b7c099b0fdcf842ab6aa550d4d90
  - f422abdf2bcbe75e4f43f879a962dbb0 --adjacent--> 98fbc94da1e7de410987462e573bf31a
  - f422abdf2bcbe75e4f43f879a962dbb0 --adjacent--> 21bb56be795390589bfa354429b20d78
  - f422abdf2bcbe75e4f43f879a962dbb0 --adjacent--> a6dafcadd49b6110f3e3d724bc4859a0
  - f422abdf2bcbe75e4f43f879a962dbb0 --adjacent--> 01207320b65ad5077a8598471e499038

---

### q4: What services does a Ziebart franchise offer?

**Seeds:** 5 | **Expanded:** 13 | **Edges:** 8 | **Tokens:** 4683

**Query Normalization:**
  - Q0: `What services does a Ziebart franchise offer?`
  - Q1: `franchise services ziebart offer what services`

**Seed Pages:** [8, 9, 15, 32, 126]

**Seed Sections:** ['Appendix', 'Methodology']

**Evidence Recall:** PASS ✓
  - Reason: Page 9 found in context

**Keywords:** 4/5 matched

**Answer:**

> A Ziebart franchise is a specialty automotive business that sells protection, detailing, window tint, and accessories services [seed:9]. The required product/service categories include:

- **Structural protective coatings:** rust protection, sound deadener, and undercoating [seed:9]  
- **Detailing and appearance protective coatings:** interior/exterior reconditioning, paint protection, fabric protection, vinyl protection, washing, polishing, and waxing [seed:9]  
- **Scratch repair:** scratch a...

**Citations:** 2
  - seed: page 9
  - seed:9; seed: page 126

**Expanded Nodes:** 13
  - ad395ea673fe3e17c6b73844c80270ad | chunk | page=8 | label=None
  - 596f1f9da21a980c028514fd3754afa9 | chunk | page=9 | label=None
  - 0af0d414507af06fc2573b73751c9f24 | chunk | page=15 | label=None
  - aae830aa7edec3612e8b1b2263f94c7a | chunk | page=32 | label=None
  - 199277b020c158fa4e0762befba61c8e | chunk | page=126 | label=None
  - 807e422698046126905222dd27644fd5 | chunk | page=8 | label=None
  - 50c611560e036741a8d4cb10cd5fc66c | chunk | page=9 | label=None
  - f5dde69ad6d2c1b57293d42772b1b05b | chunk | page=15 | label=None
  - 6d1be3dc0274b75509c6a70082b1f5d6 | chunk | page=16 | label=None
  - d6d1978e8dd6a1b5b791f316c51f21a0 | chunk | page=31 | label=None

**Edge Trace:** 8
  - 0af0d414507af06fc2573b73751c9f24 --adjacent--> 807e422698046126905222dd27644fd5
  - 0af0d414507af06fc2573b73751c9f24 --adjacent--> 50c611560e036741a8d4cb10cd5fc66c
  - 0af0d414507af06fc2573b73751c9f24 --adjacent--> f5dde69ad6d2c1b57293d42772b1b05b
  - 0af0d414507af06fc2573b73751c9f24 --adjacent--> 6d1be3dc0274b75509c6a70082b1f5d6
  - 0af0d414507af06fc2573b73751c9f24 --adjacent--> d6d1978e8dd6a1b5b791f316c51f21a0
  - 0af0d414507af06fc2573b73751c9f24 --adjacent--> 2cad5c3d93e6d6c65c8f620d4866c1d2
  - 0af0d414507af06fc2573b73751c9f24 --adjacent--> 1a591507d8cda892fd6a27747d2051a5
  - 0af0d414507af06fc2573b73751c9f24 --adjacent--> 46568c373d15d3fee26b2d8be32a385c

---

### q5: Who is the Chairman of the Board of Ziebart International Corporation?

**Seeds:** 5 | **Expanded:** 14 | **Edges:** 9 | **Tokens:** 4482

**Query Normalization:**
  - Q0: `Who is the Chairman of the Board of Ziebart International Corporation?`
  - Q1: `international board ziebart corporation chairman`

**Seed Pages:** [8, 11, 12, 239, 242]

**Seed Sections:** ['Discussion']

**Evidence Recall:** PASS ✓
  - Reason: Page 11 found in context

**Keywords:** 2/2 matched

**Answer:**

> The Chairman of the Board of Ziebart International Corporation (ZInt) is **Thomas E. Wolfe** [seed:11].

**Citations:** 1
  - seed: page 11

**Expanded Nodes:** 14
  - ad395ea673fe3e17c6b73844c80270ad | chunk | page=8 | label=None
  - 956fa4aeaeecdc8b3788ca927faa6017 | chunk | page=11 | label=None
  - 415c9d0dc49f0479e99eda4a3e78ff0c | chunk | page=12 | label=None
  - e4647beadd8e8be6eefad5287b35b0e4 | chunk | page=239 | label=None
  - 4cf23925c1eac48b9fd5eff3daa4f491 | chunk | page=242 | label=None
  - 807e422698046126905222dd27644fd5 | chunk | page=8 | label=None
  - 596f1f9da21a980c028514fd3754afa9 | chunk | page=9 | label=None
  - 2754d667481fcc3354cca13a4c020570 | chunk | page=10 | label=None
  - ccd1e738167bf3e705d01ddb36edcc70 | chunk | page=11 | label=None
  - 9c048918b40e9f930c329ade59c8866b | chunk | page=13 | label=None

**Edge Trace:** 9
  - e4647beadd8e8be6eefad5287b35b0e4 --adjacent--> 807e422698046126905222dd27644fd5
  - e4647beadd8e8be6eefad5287b35b0e4 --adjacent--> 596f1f9da21a980c028514fd3754afa9
  - e4647beadd8e8be6eefad5287b35b0e4 --adjacent--> 2754d667481fcc3354cca13a4c020570
  - e4647beadd8e8be6eefad5287b35b0e4 --adjacent--> ccd1e738167bf3e705d01ddb36edcc70
  - e4647beadd8e8be6eefad5287b35b0e4 --adjacent--> 9c048918b40e9f930c329ade59c8866b
  - e4647beadd8e8be6eefad5287b35b0e4 --adjacent--> d6d2b6a1951a9138fbe7d462d815af20
  - e4647beadd8e8be6eefad5287b35b0e4 --adjacent--> b7f1fdfb421d13fbcb35cac4ff2f66c1
  - e4647beadd8e8be6eefad5287b35b0e4 --adjacent--> 2fa1d85febec9893c612901850cfab9d
  - e4647beadd8e8be6eefad5287b35b0e4 --adjacent--> cf3585d12e77185af781d098a030cf32

---

### q6: What is the estimated initial investment range for a Ziebart franchise?

**Seeds:** 5 | **Expanded:** 9 | **Edges:** 4 | **Tokens:** 3641

**Query Normalization:**
  - Q0: `What is the estimated initial investment range for a Ziebart franchise?`
  - Q1: `ziebart estimated range initial investment`

**Seed Pages:** [15, 16, 25, 26]

**Seed Sections:** ['Methodology']

**Evidence Recall:** FAIL ✗
  - Reason: No evidence match

**Keywords:** 2/2 matched

**Answer:**

> The estimated initial investment range for a Ziebart® franchise is **$425,100 to $899,000** [adjacent:24].

**Citations:** 1
  - adjacent: page 24

**Expanded Nodes:** 9
  - 0af0d414507af06fc2573b73751c9f24 | chunk | page=15 | label=None
  - 6d1be3dc0274b75509c6a70082b1f5d6 | chunk | page=16 | label=None
  - 635f421dffb1df173cd70de2be06f4c4 | chunk | page=25 | label=None
  - c5601e261fff12138b26b087acd82a58 | chunk | page=25 | label=None
  - 8b58b58d8ad651b361cf1b8b833a008b | chunk | page=26 | label=None
  - f5dde69ad6d2c1b57293d42772b1b05b | chunk | page=15 | label=None
  - 7df3c3398e958c1a097af6a423dcf94f | chunk | page=16 | label=None
  - 646b26390bf0c63bbd37ad77c4ac0d5a | chunk | page=24 | label=None
  - d0cdc6be95193fa28cd6173c88eb8976 | chunk | page=26 | label=None

**Edge Trace:** 4
  - 0af0d414507af06fc2573b73751c9f24 --adjacent--> f5dde69ad6d2c1b57293d42772b1b05b
  - 0af0d414507af06fc2573b73751c9f24 --adjacent--> 7df3c3398e958c1a097af6a423dcf94f
  - 0af0d414507af06fc2573b73751c9f24 --adjacent--> 646b26390bf0c63bbd37ad77c4ac0d5a
  - 0af0d414507af06fc2573b73751c9f24 --adjacent--> d0cdc6be95193fa28cd6173c88eb8976

---

### q7: What is the Multi-Unit Development Fee?

**Seeds:** 5 | **Expanded:** 15 | **Edges:** 10 | **Tokens:** 4338

**Query Normalization:**
  - Q0: `What is the Multi-Unit Development Fee?`
  - Q1: `multi-unit development development fee the multi-unit multi-unit`

**Seed Pages:** [9, 27, 46, 208, 212]

**Seed Sections:** ['Appendix', 'Conclusion', 'Methodology']

**Evidence Recall:** FAIL ✗
  - Reason: No evidence match

**Keywords:** 3/3 matched

**Answer:**

> The Multi-Unit Development Fee is a **non-refundable fee** paid to Ziebart **upon mutual execution** of the Multi-Unit Development Agreement; it is **fully earned at signing** and the agreement is not effective until the fee is paid in full and clears Ziebart’s bank [seed:212]. The fee amount is stated as **$90,000** in Exhibit C [seed:212].

**Citations:** 1
  - seed: page 212

**Expanded Nodes:** 15
  - 50c611560e036741a8d4cb10cd5fc66c | chunk | page=9 | label=None
  - 4f2e2b8df56e04fa79efa30e8e6927fd | chunk | page=27 | label=None
  - 180fabdf4381e01028e46e65042f7ea3 | chunk | page=46 | label=None
  - 5ed3f9826fe82c3a5a49faf51d338ef8 | chunk | page=208 | label=None
  - 94808cf409fb4403604385b667ed0266 | chunk | page=212 | label=None
  - 596f1f9da21a980c028514fd3754afa9 | chunk | page=9 | label=None
  - 2754d667481fcc3354cca13a4c020570 | chunk | page=10 | label=None
  - d3fa9d3bbb3c17ce419a5ba3fbc90b27 | chunk | page=27 | label=None
  - b19085a50c3a19ef1969f4924e9dd815 | chunk | page=28 | label=None
  - a84ab6a16afd0ced9230f8d8e3ff5c1b | chunk | page=47 | label=None

**Edge Trace:** 10
  - 5ed3f9826fe82c3a5a49faf51d338ef8 --adjacent--> 596f1f9da21a980c028514fd3754afa9
  - 5ed3f9826fe82c3a5a49faf51d338ef8 --adjacent--> 2754d667481fcc3354cca13a4c020570
  - 5ed3f9826fe82c3a5a49faf51d338ef8 --adjacent--> d3fa9d3bbb3c17ce419a5ba3fbc90b27
  - 5ed3f9826fe82c3a5a49faf51d338ef8 --adjacent--> b19085a50c3a19ef1969f4924e9dd815
  - 5ed3f9826fe82c3a5a49faf51d338ef8 --adjacent--> a84ab6a16afd0ced9230f8d8e3ff5c1b
  - 5ed3f9826fe82c3a5a49faf51d338ef8 --adjacent--> cd053541a2b237dfccee4f6e56a83e07
  - 5ed3f9826fe82c3a5a49faf51d338ef8 --adjacent--> 8b260a8923c9d58e0a92c7539fcee1b5
  - 5ed3f9826fe82c3a5a49faf51d338ef8 --adjacent--> 2a150d8643ba2d939f726b3852838d6b
  - 5ed3f9826fe82c3a5a49faf51d338ef8 --adjacent--> 724dc7fc37bfc3ecffdd162d7c2af282
  - 5ed3f9826fe82c3a5a49faf51d338ef8 --adjacent--> a30a4c1e2f848538b3f79c5b713deadb

---

### q8: What trademarks does Ziebart own? List at least 5.

**Seeds:** 5 | **Expanded:** 12 | **Edges:** 7 | **Tokens:** 2847

**Query Normalization:**
  - Q0: `What trademarks does Ziebart own? List at least 5.`
  - Q1: `list what trademarks least ziebart trademarks`

**Seed Pages:** [48, 50, 118, 120, 122]

**Seed Sections:** ['Appendix', 'Conclusion']

**Evidence Recall:** PASS ✓
  - Reason: Page 51 found in context

**Keywords:** 5/5 matched

**Answer:**

> Ziebart (ZInt) owns the following registered trademarks (among others): ZIEBART® [seed:48], IT’S US. OR RUST® [seed:48], ZEEGARD® [seed:48], ZEE-GLAZE® [seed:48], FORMULA Z® [seed:48], INNER-CLEAN® [seed:50], TIDY CAR® [seed:50], Z-LINER® [seed:50], Z-SHIELD® [seed:50], and DIAMOND GLOSS® [seed:50].

**Citations:** 2
  - seed: page 48
  - seed: page 50

**Expanded Nodes:** 12
  - 759afd391087863d0f35ad9f26d300b7 | chunk | page=48 | label=None
  - c66871c4b77e87d7171572c4d353fb8a | chunk | page=50 | label=None
  - b29785f08f1073e1a002bc3c4e32db76 | chunk | page=118 | label=None
  - 752b7f2d99e3a40176c5ec190bb87f26 | chunk | page=120 | label=None
  - 6ee15a9adda4a5d50f603b3842853ad7 | chunk | page=122 | label=None
  - a84ab6a16afd0ced9230f8d8e3ff5c1b | chunk | page=47 | label=None
  - 9dea3d7cf730cdb2a24504b7332bf68a | chunk | page=49 | label=None
  - 6952d5b23ca401148741ec2bb518c939 | chunk | page=51 | label=None
  - e14b0e4c19b915b3e7e2ea7670007afc | chunk | page=117 | label=None
  - a13fa81afe772c557ae10253aac7513a | chunk | page=119 | label=None

**Edge Trace:** 7
  - b29785f08f1073e1a002bc3c4e32db76 --adjacent--> a84ab6a16afd0ced9230f8d8e3ff5c1b
  - b29785f08f1073e1a002bc3c4e32db76 --adjacent--> 9dea3d7cf730cdb2a24504b7332bf68a
  - b29785f08f1073e1a002bc3c4e32db76 --adjacent--> 6952d5b23ca401148741ec2bb518c939
  - b29785f08f1073e1a002bc3c4e32db76 --adjacent--> e14b0e4c19b915b3e7e2ea7670007afc
  - b29785f08f1073e1a002bc3c4e32db76 --adjacent--> a13fa81afe772c557ae10253aac7513a
  - b29785f08f1073e1a002bc3c4e32db76 --adjacent--> c5029eb956ea61afae821459fe885f30
  - b29785f08f1073e1a002bc3c4e32db76 --adjacent--> 7b1ebbbe031c4486700c4f694d7a89ab

---

### q9: What happens to the franchise upon termination according to the agreement?

**ERROR:** No matching chunks found for question

### q10: What is the address of Ziebart Corporation headquarters?

**Seeds:** 5 | **Expanded:** 12 | **Edges:** 7 | **Tokens:** 4353

**Query Normalization:**
  - Q0: `What is the address of Ziebart Corporation headquarters?`
  - Q1: `the address address ziebart corporation headquarters`

**Seed Pages:** [8, 242, 260, 261]

**Seed Sections:** ['Conclusion', 'Discussion']

**Evidence Recall:** PASS ✓
  - Reason: Page 8 found in context

**Keywords:** 3/4 matched

**Answer:**

> Ziebart Corporation’s headquarters (principal business address) is **1290 E. Maple, Troy, Michigan 48083** [seed:8].

**Citations:** 1
  - seed: page 8

**Expanded Nodes:** 12
  - 807e422698046126905222dd27644fd5 | chunk | page=8 | label=None
  - ad395ea673fe3e17c6b73844c80270ad | chunk | page=8 | label=None
  - 4cf23925c1eac48b9fd5eff3daa4f491 | chunk | page=242 | label=None
  - 5783ddc22649ed2633a2b00a68e74452 | chunk | page=260 | label=None
  - 5f88b2fef750370501bf73b779ee3bd2 | chunk | page=261 | label=None
  - a4e694a19e5ae7488ef7be7df5d53226 | chunk | page=7 | label=None
  - 596f1f9da21a980c028514fd3754afa9 | chunk | page=9 | label=None
  - 2fa1d85febec9893c612901850cfab9d | chunk | page=241 | label=None
  - cf3585d12e77185af781d098a030cf32 | chunk | page=243 | label=None
  - 4b9b1dc9d64e5a9327587a3b8cf6a660 | chunk | page=260 | label=None

**Edge Trace:** 7
  - 807e422698046126905222dd27644fd5 --adjacent--> a4e694a19e5ae7488ef7be7df5d53226
  - 807e422698046126905222dd27644fd5 --adjacent--> 596f1f9da21a980c028514fd3754afa9
  - 807e422698046126905222dd27644fd5 --adjacent--> 2fa1d85febec9893c612901850cfab9d
  - 807e422698046126905222dd27644fd5 --adjacent--> cf3585d12e77185af781d098a030cf32
  - 807e422698046126905222dd27644fd5 --adjacent--> 4b9b1dc9d64e5a9327587a3b8cf6a660
  - 807e422698046126905222dd27644fd5 --adjacent--> eb233954d72f93a594f4b51ddb94561f
  - 807e422698046126905222dd27644fd5 --adjacent--> 77f9d685288c9063eb3fdab56fa688b9

---

### q11: What is the opening inventory cost range for a Ziebart franchise?

**Seeds:** 5 | **Expanded:** 11 | **Edges:** 6 | **Tokens:** 4530

**Query Normalization:**
  - Q0: `What is the opening inventory cost range for a Ziebart franchise?`
  - Q1: `opening ziebart inventory range cost`

**Seed Pages:** [15, 16, 25, 26, 82]

**Seed Sections:** ['Conclusion', 'Methodology']

**Evidence Recall:** PASS ✓
  - Reason: Page 15 found in context

**Keywords:** 3/3 matched

**Answer:**

> The opening inventory package for a Ziebart® franchise costs between **$32,000 and $50,000** (shipping costs are your responsibility) [seed:15].

**Citations:** 1
  - seed: page 15

**Expanded Nodes:** 11
  - 0af0d414507af06fc2573b73751c9f24 | chunk | page=15 | label=None
  - 6d1be3dc0274b75509c6a70082b1f5d6 | chunk | page=16 | label=None
  - c5601e261fff12138b26b087acd82a58 | chunk | page=25 | label=None
  - 8b58b58d8ad651b361cf1b8b833a008b | chunk | page=26 | label=None
  - 8d29a3f3c7100edf447b34479a2ec6e1 | chunk | page=82 | label=None
  - f5dde69ad6d2c1b57293d42772b1b05b | chunk | page=15 | label=None
  - 7df3c3398e958c1a097af6a423dcf94f | chunk | page=16 | label=None
  - 635f421dffb1df173cd70de2be06f4c4 | chunk | page=25 | label=None
  - d0cdc6be95193fa28cd6173c88eb8976 | chunk | page=26 | label=None
  - 81ae3245f0a5ddce61f04a60f8f40603 | chunk | page=81 | label=None

**Edge Trace:** 6
  - 0af0d414507af06fc2573b73751c9f24 --adjacent--> f5dde69ad6d2c1b57293d42772b1b05b
  - 0af0d414507af06fc2573b73751c9f24 --adjacent--> 7df3c3398e958c1a097af6a423dcf94f
  - 0af0d414507af06fc2573b73751c9f24 --adjacent--> 635f421dffb1df173cd70de2be06f4c4
  - 0af0d414507af06fc2573b73751c9f24 --adjacent--> d0cdc6be95193fa28cd6173c88eb8976
  - 0af0d414507af06fc2573b73751c9f24 --adjacent--> 81ae3245f0a5ddce61f04a60f8f40603
  - 0af0d414507af06fc2573b73751c9f24 --adjacent--> 96b5126cf2df95003987c260647df749

---

### q12: Are there any special provisions for Veterans?

**Seeds:** 5 | **Expanded:** 13 | **Edges:** 8 | **Tokens:** 4482

**Query Normalization:**
  - Q0: `Are there any special provisions for Veterans?`
  - Q1: `any veterans provisions there any special`

**Seed Pages:** [14, 15, 159, 161, 201]

**Seed Sections:** ['Appendix']

**Evidence Recall:** PASS ✓
  - Reason: Page 15 found in context

**Keywords:** 3/3 matched

**Answer:**

> Yes. Under Ziebart’s **Veteran Franchise Fee Discount Program**, Ziebart will **waive the Initial Franchise Fee** for **qualified veterans** (honorably discharged or currently serving and eligible for an honorable discharge) [seed:14]. Qualified veterans must pay a **non-refundable $20,000 Deposit Fee** that is **credited to the Start-Up Order** upon signing the Franchise Agreement [seed:14].

If a qualified veteran enters into a **Development Agreement**, the veteran pays a **non-refundable Dev...

**Citations:** 2
  - seed: page 14
  - seed: page 15

**Expanded Nodes:** 13
  - 6fd76dc70d15b4406ba0511b7e479c4c | chunk | page=14 | label=None
  - f5dde69ad6d2c1b57293d42772b1b05b | chunk | page=15 | label=None
  - 88f55c64bc08e00a1f84d019e61d5148 | chunk | page=159 | label=None
  - 5256127e49782f63c2e08c7c348afaa8 | chunk | page=161 | label=None
  - a65bbb958eb66abe442fbd3cb999527f | chunk | page=201 | label=None
  - a1c6de92034e334c558e367fcb0f128f | chunk | page=14 | label=None
  - 0af0d414507af06fc2573b73751c9f24 | chunk | page=15 | label=None
  - 907c3d867dc70ca8adc67472a4159547 | chunk | page=158 | label=None
  - 87985e1db11dfa37ea7c947e2ba158a4 | chunk | page=160 | label=None
  - 0a5a8148557e0e1844a3d694a12c5954 | chunk | page=161 | label=None

**Edge Trace:** 8
  - 5256127e49782f63c2e08c7c348afaa8 --adjacent--> a1c6de92034e334c558e367fcb0f128f
  - 5256127e49782f63c2e08c7c348afaa8 --adjacent--> 0af0d414507af06fc2573b73751c9f24
  - 5256127e49782f63c2e08c7c348afaa8 --adjacent--> 907c3d867dc70ca8adc67472a4159547
  - 5256127e49782f63c2e08c7c348afaa8 --adjacent--> 87985e1db11dfa37ea7c947e2ba158a4
  - 5256127e49782f63c2e08c7c348afaa8 --adjacent--> 0a5a8148557e0e1844a3d694a12c5954
  - 5256127e49782f63c2e08c7c348afaa8 --adjacent--> 93c89ac081ec99c1f955370c8358ace9
  - 5256127e49782f63c2e08c7c348afaa8 --adjacent--> 39975668459cc8ae2321eae5d82c05ef
  - 5256127e49782f63c2e08c7c348afaa8 --adjacent--> 4a0274c225857072f6e67f911a2fc6c9

---

### q13: What is required regarding the warranty program and NALF?

**Seeds:** 5 | **Expanded:** 15 | **Edges:** 10 | **Tokens:** 6130

**Query Normalization:**
  - Q0: `What is required regarding the warranty program and NALF?`
  - Q1: `program warranty regarding required nalf`

**Seed Pages:** [17, 20, 86, 90, 131]

**Seed Sections:** ['Appendix', 'Conclusion']

**Evidence Recall:** PASS ✓
  - Reason: Page 20 found in context

**Keywords:** 3/3 matched

**Answer:**

> - You are required to offer certain warranties, and for services warranted under the Ziebart® Trademarks you may issue only approved warranties (you must “issue only the warranties we have approved”) [seed:20] [seed:86].  
- The warranty program is operated under the North American Liability Fund (NALF) and is self-funded [seed:20].  
- You are required to join and participate in NALF [seed:86] [seed:90].  
- You must issue NALF warranties for new and used vehicles owned for personal use, and fo...

**Citations:** 3
  - seed: page 20
  - seed: page 86
  - seed: page 90

**Expanded Nodes:** 15
  - d1852832fd4cb40781c7524030a00d57 | chunk | page=17 | label=None
  - 98fbc94da1e7de410987462e573bf31a | chunk | page=20 | label=None
  - 2c5c63014f1fcfacf099838396ea71ed | chunk | page=86 | label=None
  - 91993c1f981b4973a0f1a012f408d275 | chunk | page=90 | label=None
  - 581d78a705190cc366f2f48ba614387b | chunk | page=131 | label=None
  - c4871760f79359a6eedb36d4297ebe82 | chunk | page=17 | label=None
  - 083406ffd30e6804778be302477b3596 | chunk | page=18 | label=None
  - 61f9f9818b8a088542c0a840629c7db0 | chunk | page=20 | label=None
  - 13fec372ac78a60df084887c05aead87 | chunk | page=21 | label=None
  - 9812a20def40db1d382773bf39d7f2ca | chunk | page=85 | label=None

**Edge Trace:** 10
  - 98fbc94da1e7de410987462e573bf31a --adjacent--> c4871760f79359a6eedb36d4297ebe82
  - 98fbc94da1e7de410987462e573bf31a --adjacent--> 083406ffd30e6804778be302477b3596
  - 98fbc94da1e7de410987462e573bf31a --adjacent--> 61f9f9818b8a088542c0a840629c7db0
  - 98fbc94da1e7de410987462e573bf31a --adjacent--> 13fec372ac78a60df084887c05aead87
  - 98fbc94da1e7de410987462e573bf31a --adjacent--> 9812a20def40db1d382773bf39d7f2ca
  - 98fbc94da1e7de410987462e573bf31a --adjacent--> bd87177e3b0656a031ea934da5eadb5c
  - 98fbc94da1e7de410987462e573bf31a --adjacent--> fedde5a4e97fb8c4638546b27b9082c6
  - 98fbc94da1e7de410987462e573bf31a --adjacent--> 5396763356afe1eb6ec30684fdb1a3c4
  - 98fbc94da1e7de410987462e573bf31a --adjacent--> adbd4bec6f5dcfa4cad2bf2bac1cdad1
  - 98fbc94da1e7de410987462e573bf31a --adjacent--> c6488ec5b5d291087aefd3f8d1c8c80f

---

### q14: What are the Michigan state-specific disclosure requirements?

**Seeds:** 5 | **Expanded:** 11 | **Edges:** 6 | **Tokens:** 4567

**Query Normalization:**
  - Q0: `What are the Michigan state-specific disclosure requirements?`
  - Q1: `state-specific disclosure michigan the michigan requirements`

**Seed Pages:** [4, 5, 6, 157, 158]

**Seed Sections:** ['Appendix']

**Evidence Recall:** PASS ✓
  - Reason: Page 6 found in context

**Keywords:** 2/3 matched

**Answer:**

> Michigan state-specific disclosures in the provided context include:

- **Notice of prohibited practices / void provisions:** Michigan prohibits certain unfair provisions in franchise documents; if included, they are **void and unenforceable**. These include (among others) provisions that: prohibit joining a franchisee association; require waivers/releases that deprive statutory rights; allow termination before term end without “good cause” (with notice and up to 30 days to cure); allow nonrenew...

**Citations:** 4
  - seed: page 5
  - seed: page 6
  - seed: page 157
  - seed: page 158

**Expanded Nodes:** 11
  - 63f517d307e5b0b177087f7edc739fbd | chunk | page=4 | label=None
  - 6088cfa58ba1401a66e9fcec0c5e1ea8 | chunk | page=5 | label=None
  - fe59ae2db71876459cea34a6b425e0f5 | chunk | page=6 | label=None
  - 097927e5c1dbe4b27047d82b13796227 | chunk | page=157 | label=None
  - 907c3d867dc70ca8adc67472a4159547 | chunk | page=158 | label=None
  - 17e6694087eac0440d0dbda4369f4aef | chunk | page=3 | label=None
  - 1ee57f061d780559e29bf149d194903c | chunk | page=5 | label=None
  - a4e694a19e5ae7488ef7be7df5d53226 | chunk | page=7 | label=None
  - 456e96c52cb900d34dd060e01ad1dc07 | chunk | page=156 | label=None
  - b00663dd46ad6c9ce53e8e79bcb540e9 | chunk | page=157 | label=None

**Edge Trace:** 6
  - 63f517d307e5b0b177087f7edc739fbd --adjacent--> 17e6694087eac0440d0dbda4369f4aef
  - 63f517d307e5b0b177087f7edc739fbd --adjacent--> 1ee57f061d780559e29bf149d194903c
  - 63f517d307e5b0b177087f7edc739fbd --adjacent--> a4e694a19e5ae7488ef7be7df5d53226
  - 63f517d307e5b0b177087f7edc739fbd --adjacent--> 456e96c52cb900d34dd060e01ad1dc07
  - 63f517d307e5b0b177087f7edc739fbd --adjacent--> b00663dd46ad6c9ce53e8e79bcb540e9
  - 63f517d307e5b0b177087f7edc739fbd --adjacent--> 88f55c64bc08e00a1f84d019e61d5148

---

### q15: Is there any pending litigation disclosed?

**Seeds:** 5 | **Expanded:** 13 | **Edges:** 8 | **Tokens:** 4159

**Query Normalization:**
  - Q0: `Is there any pending litigation disclosed?`
  - Q1: `pending disclosed any litigation there any`

**Seed Pages:** [13, 164, 199, 256]

**Seed Sections:** ['Appendix', 'Conclusion']

**Evidence Recall:** PASS ✓
  - Reason: Page 13 found in context

**Keywords:** 3/3 matched

**Answer:**

> Item 3 states that no litigation is required to be disclosed [seed:13]. The New York addendum further states that there are no administrative, criminal, or civil actions pending against the franchisor (or related persons/affiliates) alleging specified violations [seed:164].

**Citations:** 2
  - seed: page 13
  - seed: page 164

**Expanded Nodes:** 13
  - 9c048918b40e9f930c329ade59c8866b | chunk | page=13 | label=None
  - 18b25d67ee179a15187b404430fe585e | chunk | page=164 | label=None
  - b15dddc5ce7743e013e498f9301da664 | chunk | page=164 | label=None
  - e3ddf1631a14840c9affef87ba2ba53f | chunk | page=199 | label=None
  - 6c3c17c9c9507c8cbe212dd6141b2aee | chunk | page=256 | label=None
  - 415c9d0dc49f0479e99eda4a3e78ff0c | chunk | page=12 | label=None
  - a1c6de92034e334c558e367fcb0f128f | chunk | page=14 | label=None
  - 3e6e244ae2c19aff56de75a6e011e6f9 | chunk | page=163 | label=None
  - bdc3efc69e638e871c0afffd7815a6c5 | chunk | page=165 | label=None
  - ad6bc7cd14e25095bac6ee131e65cda0 | chunk | page=198 | label=None

**Edge Trace:** 8
  - e3ddf1631a14840c9affef87ba2ba53f --adjacent--> 415c9d0dc49f0479e99eda4a3e78ff0c
  - e3ddf1631a14840c9affef87ba2ba53f --adjacent--> a1c6de92034e334c558e367fcb0f128f
  - e3ddf1631a14840c9affef87ba2ba53f --adjacent--> 3e6e244ae2c19aff56de75a6e011e6f9
  - e3ddf1631a14840c9affef87ba2ba53f --adjacent--> bdc3efc69e638e871c0afffd7815a6c5
  - e3ddf1631a14840c9affef87ba2ba53f --adjacent--> ad6bc7cd14e25095bac6ee131e65cda0
  - e3ddf1631a14840c9affef87ba2ba53f --adjacent--> 79591579742ec6a83bfc7bb286ea99f7
  - e3ddf1631a14840c9affef87ba2ba53f --adjacent--> 7acbfc1a8f962e331ec88e424692e656
  - e3ddf1631a14840c9affef87ba2ba53f --adjacent--> 1ff09c29eee3160552258c94400ba0fc

---

### q16: What is the training cancellation fee?

**Seeds:** 5 | **Expanded:** 11 | **Edges:** 6 | **Tokens:** 4629

**Query Normalization:**
  - Q0: `What is the training cancellation fee?`
  - Q1: `cancellation fee training cancellation the training training`

**Seed Pages:** [17, 18, 43, 44, 141]

**Seed Sections:** ['Appendix', 'Conclusion']

**Evidence Recall:** PASS ✓
  - Reason: Page 18 found in context

**Keywords:** 3/3 matched

**Answer:**

> The training cancellation fee is **$100 per occurrence**, plus **any non-refundable airfare** for trips purchased by the trainers, if training is cancelled within **7 days** of the scheduled start time [seed:18].

**Citations:** 1
  - seed: page 18

**Expanded Nodes:** 11
  - d1852832fd4cb40781c7524030a00d57 | chunk | page=17 | label=None
  - 083406ffd30e6804778be302477b3596 | chunk | page=18 | label=None
  - 71c74e697cf94c57dd2550029e5fee34 | chunk | page=43 | label=None
  - 9eac9c3cccb65b7367430e9c375f4d7c | chunk | page=44 | label=None
  - 52c4e0bc8edaa9a16ae936e488bda4ac | chunk | page=141 | label=None
  - c4871760f79359a6eedb36d4297ebe82 | chunk | page=17 | label=None
  - 5eebc8f832510c5e221c62c7c33607a4 | chunk | page=19 | label=None
  - a12fad7544a0fe6d56cad7d788e43d60 | chunk | page=42 | label=None
  - f37b54c4b03d24191026fb2239d0f30c | chunk | page=45 | label=None
  - e0b51fc13745fac1a83c4fc125451e0a | chunk | page=140 | label=None

**Edge Trace:** 6
  - 52c4e0bc8edaa9a16ae936e488bda4ac --adjacent--> c4871760f79359a6eedb36d4297ebe82
  - 52c4e0bc8edaa9a16ae936e488bda4ac --adjacent--> 5eebc8f832510c5e221c62c7c33607a4
  - 52c4e0bc8edaa9a16ae936e488bda4ac --adjacent--> a12fad7544a0fe6d56cad7d788e43d60
  - 52c4e0bc8edaa9a16ae936e488bda4ac --adjacent--> f37b54c4b03d24191026fb2239d0f30c
  - 52c4e0bc8edaa9a16ae936e488bda4ac --adjacent--> e0b51fc13745fac1a83c4fc125451e0a
  - 52c4e0bc8edaa9a16ae936e488bda4ac --adjacent--> 877a7d1547925f5b3c04ee11e60a454c

---

### q17: Who is the Vice President of Information Technology at Ziebart?

**Seeds:** 5 | **Expanded:** 11 | **Edges:** 6 | **Tokens:** 3589

**Query Normalization:**
  - Q0: `Who is the Vice President of Information Technology at Ziebart?`
  - Q1: `vice ziebart technology information president`

**Seed Pages:** [8, 11, 12, 261]

**Seed Sections:** ['Conclusion']

**Evidence Recall:** PASS ✓
  - Reason: Page 12 found in context

**Keywords:** 3/3 matched

**Answer:**

> The Vice President of Information Technology at Ziebart is **Larry Stewart** [seed:12].

**Citations:** 1
  - seed: page 12

**Expanded Nodes:** 11
  - ad395ea673fe3e17c6b73844c80270ad | chunk | page=8 | label=None
  - 956fa4aeaeecdc8b3788ca927faa6017 | chunk | page=11 | label=None
  - ccd1e738167bf3e705d01ddb36edcc70 | chunk | page=11 | label=None
  - 415c9d0dc49f0479e99eda4a3e78ff0c | chunk | page=12 | label=None
  - 5f88b2fef750370501bf73b779ee3bd2 | chunk | page=261 | label=None
  - 807e422698046126905222dd27644fd5 | chunk | page=8 | label=None
  - 596f1f9da21a980c028514fd3754afa9 | chunk | page=9 | label=None
  - 2754d667481fcc3354cca13a4c020570 | chunk | page=10 | label=None
  - 9c048918b40e9f930c329ade59c8866b | chunk | page=13 | label=None
  - eb233954d72f93a594f4b51ddb94561f | chunk | page=261 | label=None

**Edge Trace:** 6
  - ccd1e738167bf3e705d01ddb36edcc70 --adjacent--> 807e422698046126905222dd27644fd5
  - ccd1e738167bf3e705d01ddb36edcc70 --adjacent--> 596f1f9da21a980c028514fd3754afa9
  - ccd1e738167bf3e705d01ddb36edcc70 --adjacent--> 2754d667481fcc3354cca13a4c020570
  - ccd1e738167bf3e705d01ddb36edcc70 --adjacent--> 9c048918b40e9f930c329ade59c8866b
  - ccd1e738167bf3e705d01ddb36edcc70 --adjacent--> eb233954d72f93a594f4b51ddb94561f
  - ccd1e738167bf3e705d01ddb36edcc70 --adjacent--> 77f9d685288c9063eb3fdab56fa688b9

---

### q18: What is the Rhino Linings relationship with Ziebart?

**Seeds:** 5 | **Expanded:** 14 | **Edges:** 9 | **Tokens:** 5179

**Query Normalization:**
  - Q0: `What is the Rhino Linings relationship with Ziebart?`
  - Q1: `the rhino rhino relationship linings ziebart`

**Seed Pages:** [8, 52, 53, 124, 136]

**Seed Sections:** ['Appendix', 'Conclusion']

**Evidence Recall:** PASS ✓
  - Reason: Page 53 found in context

**Keywords:** 3/3 matched

**Answer:**

> Rhino Linings Corporation (“Rhino”) has a supplier/development relationship with Ziebart (through Ziebart International Corporation (“ZInt”) and Ziebart Corporation (“ZC”)) that allows Ziebart to sublicense Rhino’s products and trademarks to Ziebart franchisees:

- ZInt and Rhino entered into a Development Agreement (restated June 15, 2009; originally dating back to 1999) granting ZC a limited exclusive right to sublicense to Ziebart® businesses the right to sell and apply automotive application...

**Citations:** 4
  - seed:53; seed: page 136
  - seed:53; adjacen: page 9
  - seed: page 124
  - seed: page 53

**Expanded Nodes:** 14
  - ad395ea673fe3e17c6b73844c80270ad | chunk | page=8 | label=None
  - 8bd720645f1910f1663627bd98d0e170 | chunk | page=52 | label=None
  - 17550d44bfca66d54b69b6f622fd5143 | chunk | page=53 | label=None
  - 9e25947591773fb540149009dcf4558c | chunk | page=124 | label=None
  - f9c0cbcf1479e8b44b663ceec4b013f9 | chunk | page=136 | label=None
  - 807e422698046126905222dd27644fd5 | chunk | page=8 | label=None
  - 596f1f9da21a980c028514fd3754afa9 | chunk | page=9 | label=None
  - 6952d5b23ca401148741ec2bb518c939 | chunk | page=51 | label=None
  - 618f75e0a37741c03b7038f9d6b24cde | chunk | page=53 | label=None
  - 93b720c70df5408de2f8aabedfcf8144 | chunk | page=54 | label=None

**Edge Trace:** 9
  - f9c0cbcf1479e8b44b663ceec4b013f9 --adjacent--> 807e422698046126905222dd27644fd5
  - f9c0cbcf1479e8b44b663ceec4b013f9 --adjacent--> 596f1f9da21a980c028514fd3754afa9
  - f9c0cbcf1479e8b44b663ceec4b013f9 --adjacent--> 6952d5b23ca401148741ec2bb518c939
  - f9c0cbcf1479e8b44b663ceec4b013f9 --adjacent--> 618f75e0a37741c03b7038f9d6b24cde
  - f9c0cbcf1479e8b44b663ceec4b013f9 --adjacent--> 93b720c70df5408de2f8aabedfcf8144
  - f9c0cbcf1479e8b44b663ceec4b013f9 --adjacent--> 7b1ebbbe031c4486700c4f694d7a89ab
  - f9c0cbcf1479e8b44b663ceec4b013f9 --adjacent--> 1a591507d8cda892fd6a27747d2051a5
  - f9c0cbcf1479e8b44b663ceec4b013f9 --adjacent--> fd0902ec07ecc846c7a88b0a48c2ff1b
  - f9c0cbcf1479e8b44b663ceec4b013f9 --adjacent--> 63722eda74b41d1a329c3ae9fcccd3ec

---

### q19: What are the provisions for Washington state franchisees?

**Seeds:** 5 | **Expanded:** 10 | **Edges:** 5 | **Tokens:** 3903

**Query Normalization:**
  - Q0: `What are the provisions for Washington state franchisees?`
  - Q1: `state washington provisions the provisions franchisees`

**Seed Pages:** [161, 162, 201]

**Seed Sections:** ['Appendix']

**Evidence Recall:** PASS ✓
  - Reason: Page 201 found in context

**Keywords:** 3/3 matched

**Answer:**

> For Washington franchisees, Addendum S provides (and may override conflicting franchise agreement terms) that:

- **Conflict of laws:** If laws conflict, the **Washington Franchise Investment Protection Act (WFIPA), RCW 19.100** prevails. [seed:161]  
- **Franchisee Bill of Rights / state law controls:** **RCW 19.100.180** and court decisions may supersede the franchise agreement (including termination/renewal provisions). [seed:161]  
- **Arbitration/mediation/litigation venue:** Arbitration/me...

**Citations:** 4
  - seed: page 161
  - seed: page 162
  - adjacent: page 163
  - adjacent: page 202

**Expanded Nodes:** 10
  - 0a5a8148557e0e1844a3d694a12c5954 | chunk | page=161 | label=None
  - 5256127e49782f63c2e08c7c348afaa8 | chunk | page=161 | label=None
  - 9aa5bd4b3497968ad7fdd4579db9f609 | chunk | page=162 | label=None
  - d2dea2c6aed3b169ca9a4c1223633723 | chunk | page=162 | label=None
  - 4a0274c225857072f6e67f911a2fc6c9 | chunk | page=201 | label=None
  - 87985e1db11dfa37ea7c947e2ba158a4 | chunk | page=160 | label=None
  - 93c89ac081ec99c1f955370c8358ace9 | chunk | page=161 | label=None
  - 3e6e244ae2c19aff56de75a6e011e6f9 | chunk | page=163 | label=None
  - a65bbb958eb66abe442fbd3cb999527f | chunk | page=201 | label=None
  - 04292683fc5d4461abb59d75f65377ee | chunk | page=202 | label=None

**Edge Trace:** 5
  - 5256127e49782f63c2e08c7c348afaa8 --adjacent--> 87985e1db11dfa37ea7c947e2ba158a4
  - 5256127e49782f63c2e08c7c348afaa8 --adjacent--> 93c89ac081ec99c1f955370c8358ace9
  - 5256127e49782f63c2e08c7c348afaa8 --adjacent--> 3e6e244ae2c19aff56de75a6e011e6f9
  - 5256127e49782f63c2e08c7c348afaa8 --adjacent--> a65bbb958eb66abe442fbd3cb999527f
  - 5256127e49782f63c2e08c7c348afaa8 --adjacent--> 04292683fc5d4461abb59d75f65377ee

---

### q20: What is the environmental compliance policy for Ziebart franchises?

**ERROR:** No matching chunks found for question

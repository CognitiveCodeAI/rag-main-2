# QA Evaluation Report

**Document:** C:/Apps/rag/2025 FDD.pdf
**Doc ID:** `37660ee55b1fb2aa63579e3aeb2aca97`
**Timestamp:** 2026-01-29T01:52:18.204103
**Total Time:** 86877ms

## Summary

| Metric | Value |
|--------|-------|
| Questions | 20 |
| Successful | 20 |
| Evidence Recall | 20/20 (100%) |
| Keyword Match Avg | 95.9% |

## Results by Question

| # | Question | Seeds | Expanded | Evidence | Keywords | Figures | Intent | Time |
|---|----------|-------|----------|----------|----------|---------|--------|------|
| q1 | What is the initial franchise fee f... | 5 | 10 | PASS | 3/3 | N/A | - | 5097ms |
| q2 | What is the royalty percentage that... | 5 | 14 | PASS | 3/3 | N/A | - | 2505ms |
| q3 | What is the minimum weekly royalty ... | 5 | 12 | PASS | 3/3 | N/A | - | 2345ms |
| q4 | What services does a Ziebart franch... | 5 | 13 | PASS | 4/5 | N/A | - | 3837ms |
| q5 | Who is the Chairman of the Board of... | 5 | 14 | PASS | 2/2 | N/A | - | 1638ms |
| q6 | What is the estimated initial inves... | 5 | 9 | PASS | 2/2 | N/A | - | 1715ms |
| q7 | What is the Multi-Unit Development ... | 5 | 15 | PASS | 3/3 | N/A | - | 2781ms |
| q8 | What trademarks does Ziebart own? L... | 5 | 12 | PASS | 5/5 | N/A | - | 3643ms |
| q9 | What happens to the franchise upon ... | 5 | 15 | PASS | 2/3 | N/A | - | 10266ms |
| q10 | What is the address of Ziebart Corp... | 5 | 12 | PASS | 3/4 | N/A | - | 1797ms |
| q11 | What is the opening inventory cost ... | 5 | 11 | PASS | 3/3 | N/A | - | 1724ms |
| q12 | Are there any special provisions fo... | 5 | 13 | PASS | 3/3 | N/A | - | 3947ms |
| q13 | What is required regarding the warr... | 5 | 15 | PASS | 3/3 | N/A | - | 4762ms |
| q14 | What are the Michigan state-specifi... | 5 | 11 | PASS | 3/3 | N/A | - | 8835ms |
| q15 | Is there any pending litigation dis... | 5 | 13 | PASS | 3/3 | N/A | - | 3591ms |
| q16 | What is the training cancellation f... | 5 | 11 | PASS | 3/3 | N/A | - | 2017ms |
| q17 | Who is the Vice President of Inform... | 5 | 11 | PASS | 3/3 | N/A | - | 1507ms |
| q18 | What is the Rhino Linings relations... | 5 | 14 | PASS | 3/3 | N/A | - | 5824ms |
| q19 | What are the provisions for Washing... | 5 | 10 | PASS | 3/3 | N/A | - | 16392ms |
| q20 | What is the environmental complianc... | 5 | 14 | PASS | N/A | N/A | - | 2655ms |

## Detailed Results

### q1: What is the initial franchise fee for a Ziebart franchise?

**Seeds:** 5 | **Expanded:** 10 | **Edges:** 5 | **Tokens:** 3380

**Query Normalization:**
  - Q0: `What is the initial franchise fee for a Ziebart franchise?`
  - Q1: `initial franchise ziebart fee`

**Seed Pages:** [14, 15, 16, 82]

**Seed Sections:** ['Conclusion']

**Evidence Recall:** PASS ✓
  - Reason: Value '45,000' grounded in cited context

**Keywords:** 3/3 matched

**Answer:**

> The initial franchise fee for a Ziebart® franchise is **$45,000**, payable in a lump sum when you sign the Franchise Agreement, and it is **non-refundable** [seed:14; seed:82].

**Citations:** 1
  - seed:14; seed: page 82

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
  - 6d1be3dc0274b75509c6a70082b1f5d6 --adjacent--> 9c048918b40e9f930c329ade59c8866b
  - 6d1be3dc0274b75509c6a70082b1f5d6 --adjacent--> f5dde69ad6d2c1b57293d42772b1b05b
  - 6d1be3dc0274b75509c6a70082b1f5d6 --adjacent--> 7df3c3398e958c1a097af6a423dcf94f
  - 6d1be3dc0274b75509c6a70082b1f5d6 --adjacent--> 81ae3245f0a5ddce61f04a60f8f40603
  - 6d1be3dc0274b75509c6a70082b1f5d6 --adjacent--> 96b5126cf2df95003987c260647df749

---

### q2: What is the royalty percentage that franchisees must pay?

**Seeds:** 5 | **Expanded:** 14 | **Edges:** 9 | **Tokens:** 4960

**Query Normalization:**
  - Q0: `What is the royalty percentage that franchisees must pay?`
  - Q1: `royalty franchisees percentage the royalty pay`

**Seed Pages:** [3, 16, 19, 20, 83]

**Seed Sections:** ['Conclusion']

**Evidence Recall:** PASS ✓
  - Reason: Value '8%' grounded in cited context

**Keywords:** 3/3 matched

**Answer:**

> Franchisees must pay a royalty of **8% of Gross Sales** on all products and services, **except** for certain listed products/services that are charged a **5% royalty** [seed:16] [seed:19] [seed:83].

**Citations:** 3
  - seed: page 16
  - seed: page 19
  - seed: page 83

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
  - 7df3c3398e958c1a097af6a423dcf94f --adjacent--> e09402bbe54d8fe17cfeda6c62ce67d7
  - 7df3c3398e958c1a097af6a423dcf94f --adjacent--> 63f517d307e5b0b177087f7edc739fbd
  - 7df3c3398e958c1a097af6a423dcf94f --adjacent--> c4871760f79359a6eedb36d4297ebe82
  - 7df3c3398e958c1a097af6a423dcf94f --adjacent--> 6d1be3dc0274b75509c6a70082b1f5d6
  - 7df3c3398e958c1a097af6a423dcf94f --adjacent--> 083406ffd30e6804778be302477b3596
  - 7df3c3398e958c1a097af6a423dcf94f --adjacent--> a2a5b7c099b0fdcf842ab6aa550d4d90
  - 7df3c3398e958c1a097af6a423dcf94f --adjacent--> 98fbc94da1e7de410987462e573bf31a
  - 7df3c3398e958c1a097af6a423dcf94f --adjacent--> a6dafcadd49b6110f3e3d724bc4859a0
  - 7df3c3398e958c1a097af6a423dcf94f --adjacent--> f422abdf2bcbe75e4f43f879a962dbb0

---

### q3: What is the minimum weekly royalty amount?

**Seeds:** 5 | **Expanded:** 12 | **Edges:** 7 | **Tokens:** 3959

**Query Normalization:**
  - Q0: `What is the minimum weekly royalty amount?`
  - Q1: `the minimum amount weekly minimum royalty`

**Seed Pages:** [16, 20, 21, 83, 84]

**Seed Sections:** ['Conclusion']

**Evidence Recall:** PASS ✓
  - Reason: Value '650' grounded in cited context

**Keywords:** 3/3 matched

**Answer:**

> The minimum weekly royalty amount is **not less than $650.00 per week per location** (minimum as of December 31, 2024) [seed:20].

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
  - 7df3c3398e958c1a097af6a423dcf94f --adjacent--> c4871760f79359a6eedb36d4297ebe82
  - 7df3c3398e958c1a097af6a423dcf94f --adjacent--> 6d1be3dc0274b75509c6a70082b1f5d6
  - 7df3c3398e958c1a097af6a423dcf94f --adjacent--> a2a5b7c099b0fdcf842ab6aa550d4d90
  - 7df3c3398e958c1a097af6a423dcf94f --adjacent--> 98fbc94da1e7de410987462e573bf31a
  - 7df3c3398e958c1a097af6a423dcf94f --adjacent--> 21bb56be795390589bfa354429b20d78
  - 7df3c3398e958c1a097af6a423dcf94f --adjacent--> a6dafcadd49b6110f3e3d724bc4859a0
  - 7df3c3398e958c1a097af6a423dcf94f --adjacent--> 01207320b65ad5077a8598471e499038

---

### q4: What services does a Ziebart franchise offer?

**Seeds:** 5 | **Expanded:** 13 | **Edges:** 8 | **Tokens:** 4270

**Query Normalization:**
  - Q0: `What services does a Ziebart franchise offer?`
  - Q1: `services ziebart offer franchise what services`

**Seed Pages:** [8, 9, 15, 32, 122]

**Seed Sections:** ['Appendix', 'Methodology']

**Evidence Recall:** PASS ✓
  - Reason: Value 'protection' grounded in cited context

**Keywords:** 4/5 matched

**Answer:**

> A Ziebart® franchise is a specialty business that sells protection, detailing, window tint, and accessories services in accordance with the Ziebart® System [seed:9]. The services offered include structural protective coatings (rust protection, sound deadener, undercoating), detailing and appearance protective coatings (interior/exterior reconditioning, paint/fabric/vinyl protection, washing, polishing, waxing), scratch and scuff repair, films (window tinting and Z‑Shield® paint protection film),...

**Citations:** 1
  - seed: page 9

**Expanded Nodes:** 13
  - ad395ea673fe3e17c6b73844c80270ad | chunk | page=8 | label=None
  - 596f1f9da21a980c028514fd3754afa9 | chunk | page=9 | label=None
  - 0af0d414507af06fc2573b73751c9f24 | chunk | page=15 | label=None
  - aae830aa7edec3612e8b1b2263f94c7a | chunk | page=32 | label=None
  - 6ee15a9adda4a5d50f603b3842853ad7 | chunk | page=122 | label=None
  - 807e422698046126905222dd27644fd5 | chunk | page=8 | label=None
  - 50c611560e036741a8d4cb10cd5fc66c | chunk | page=9 | label=None
  - f5dde69ad6d2c1b57293d42772b1b05b | chunk | page=15 | label=None
  - 6d1be3dc0274b75509c6a70082b1f5d6 | chunk | page=16 | label=None
  - d6d1978e8dd6a1b5b791f316c51f21a0 | chunk | page=31 | label=None

**Edge Trace:** 8
  - 596f1f9da21a980c028514fd3754afa9 --adjacent--> 807e422698046126905222dd27644fd5
  - 596f1f9da21a980c028514fd3754afa9 --adjacent--> 50c611560e036741a8d4cb10cd5fc66c
  - 596f1f9da21a980c028514fd3754afa9 --adjacent--> f5dde69ad6d2c1b57293d42772b1b05b
  - 596f1f9da21a980c028514fd3754afa9 --adjacent--> 6d1be3dc0274b75509c6a70082b1f5d6
  - 596f1f9da21a980c028514fd3754afa9 --adjacent--> d6d1978e8dd6a1b5b791f316c51f21a0
  - 596f1f9da21a980c028514fd3754afa9 --adjacent--> 2cad5c3d93e6d6c65c8f620d4866c1d2
  - 596f1f9da21a980c028514fd3754afa9 --adjacent--> c5029eb956ea61afae821459fe885f30
  - 596f1f9da21a980c028514fd3754afa9 --adjacent--> 7b1ebbbe031c4486700c4f694d7a89ab

---

### q5: Who is the Chairman of the Board of Ziebart International Corporation?

**Seeds:** 5 | **Expanded:** 14 | **Edges:** 9 | **Tokens:** 5148

**Query Normalization:**
  - Q0: `Who is the Chairman of the Board of Ziebart International Corporation?`
  - Q1: `chairman corporation ziebart international board`

**Seed Pages:** [8, 11, 12, 122, 242]

**Seed Sections:** ['Appendix', 'Discussion']

**Evidence Recall:** PASS ✓
  - Reason: Value 'Wolfe' grounded in cited context

**Keywords:** 2/2 matched

**Answer:**

> The Chairman of the Board of Ziebart International Corporation (ZInt) is **Thomas E. Wolfe** [seed:11].

**Citations:** 1
  - seed: page 11

**Expanded Nodes:** 14
  - ad395ea673fe3e17c6b73844c80270ad | chunk | page=8 | label=None
  - 956fa4aeaeecdc8b3788ca927faa6017 | chunk | page=11 | label=None
  - 415c9d0dc49f0479e99eda4a3e78ff0c | chunk | page=12 | label=None
  - 6ee15a9adda4a5d50f603b3842853ad7 | chunk | page=122 | label=None
  - 4cf23925c1eac48b9fd5eff3daa4f491 | chunk | page=242 | label=None
  - 807e422698046126905222dd27644fd5 | chunk | page=8 | label=None
  - 596f1f9da21a980c028514fd3754afa9 | chunk | page=9 | label=None
  - 2754d667481fcc3354cca13a4c020570 | chunk | page=10 | label=None
  - ccd1e738167bf3e705d01ddb36edcc70 | chunk | page=11 | label=None
  - 9c048918b40e9f930c329ade59c8866b | chunk | page=13 | label=None

**Edge Trace:** 9
  - 415c9d0dc49f0479e99eda4a3e78ff0c --adjacent--> 807e422698046126905222dd27644fd5
  - 415c9d0dc49f0479e99eda4a3e78ff0c --adjacent--> 596f1f9da21a980c028514fd3754afa9
  - 415c9d0dc49f0479e99eda4a3e78ff0c --adjacent--> 2754d667481fcc3354cca13a4c020570
  - 415c9d0dc49f0479e99eda4a3e78ff0c --adjacent--> ccd1e738167bf3e705d01ddb36edcc70
  - 415c9d0dc49f0479e99eda4a3e78ff0c --adjacent--> 9c048918b40e9f930c329ade59c8866b
  - 415c9d0dc49f0479e99eda4a3e78ff0c --adjacent--> c5029eb956ea61afae821459fe885f30
  - 415c9d0dc49f0479e99eda4a3e78ff0c --adjacent--> 7b1ebbbe031c4486700c4f694d7a89ab
  - 415c9d0dc49f0479e99eda4a3e78ff0c --adjacent--> 2fa1d85febec9893c612901850cfab9d
  - 415c9d0dc49f0479e99eda4a3e78ff0c --adjacent--> cf3585d12e77185af781d098a030cf32

---

### q6: What is the estimated initial investment range for a Ziebart franchise?

**Seeds:** 5 | **Expanded:** 9 | **Edges:** 4 | **Tokens:** 3641

**Query Normalization:**
  - Q0: `What is the estimated initial investment range for a Ziebart franchise?`
  - Q1: `investment initial ziebart range estimated`

**Seed Pages:** [15, 16, 25, 26]

**Seed Sections:** ['Methodology']

**Evidence Recall:** PASS ✓
  - Reason: Value 'low' grounded in cited context

**Keywords:** 2/2 matched

**Answer:**

> The estimated initial investment range for a Ziebart franchise is **$425,100 to $899,000** [adjacent:24].

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
  - 6d1be3dc0274b75509c6a70082b1f5d6 --adjacent--> f5dde69ad6d2c1b57293d42772b1b05b
  - 6d1be3dc0274b75509c6a70082b1f5d6 --adjacent--> 7df3c3398e958c1a097af6a423dcf94f
  - 6d1be3dc0274b75509c6a70082b1f5d6 --adjacent--> 646b26390bf0c63bbd37ad77c4ac0d5a
  - 6d1be3dc0274b75509c6a70082b1f5d6 --adjacent--> d0cdc6be95193fa28cd6173c88eb8976

---

### q7: What is the Multi-Unit Development Fee?

**Seeds:** 5 | **Expanded:** 15 | **Edges:** 10 | **Tokens:** 4338

**Query Normalization:**
  - Q0: `What is the Multi-Unit Development Fee?`
  - Q1: `multi-unit the multi-unit multi-unit development fee development`

**Seed Pages:** [9, 27, 46, 208, 212]

**Seed Sections:** ['Appendix', 'Conclusion', 'Methodology']

**Evidence Recall:** PASS ✓
  - Reason: Value '90,000' grounded in cited context

**Keywords:** 3/3 matched

**Answer:**

> The Multi-Unit Development Fee is a **non-refundable fee** paid to Ziebart when you sign the Multi-Unit Development Agreement, and it is **fully earned at signing** [seed:212]. In Exhibit C, it is stated as **$90,000** (the “Multi-Unit Development Fee”), payable upon mutual execution of the agreement (the agreement is not effective until the fee is paid and cleared) [seed:212].

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
  - 94808cf409fb4403604385b667ed0266 --adjacent--> 596f1f9da21a980c028514fd3754afa9
  - 94808cf409fb4403604385b667ed0266 --adjacent--> 2754d667481fcc3354cca13a4c020570
  - 94808cf409fb4403604385b667ed0266 --adjacent--> d3fa9d3bbb3c17ce419a5ba3fbc90b27
  - 94808cf409fb4403604385b667ed0266 --adjacent--> b19085a50c3a19ef1969f4924e9dd815
  - 94808cf409fb4403604385b667ed0266 --adjacent--> a84ab6a16afd0ced9230f8d8e3ff5c1b
  - 94808cf409fb4403604385b667ed0266 --adjacent--> cd053541a2b237dfccee4f6e56a83e07
  - 94808cf409fb4403604385b667ed0266 --adjacent--> 8b260a8923c9d58e0a92c7539fcee1b5
  - 94808cf409fb4403604385b667ed0266 --adjacent--> 2a150d8643ba2d939f726b3852838d6b
  - 94808cf409fb4403604385b667ed0266 --adjacent--> 724dc7fc37bfc3ecffdd162d7c2af282
  - 94808cf409fb4403604385b667ed0266 --adjacent--> a30a4c1e2f848538b3f79c5b713deadb

---

### q8: What trademarks does Ziebart own? List at least 5.

**Seeds:** 5 | **Expanded:** 12 | **Edges:** 7 | **Tokens:** 2847

**Query Normalization:**
  - Q0: `What trademarks does Ziebart own? List at least 5.`
  - Q1: `list trademarks ziebart what trademarks least`

**Seed Pages:** [48, 50, 118, 120, 122]

**Seed Sections:** ['Appendix', 'Conclusion']

**Evidence Recall:** PASS ✓
  - Reason: Value 'ZIEBART' grounded in cited context

**Keywords:** 5/5 matched

**Answer:**

> Ziebart (ZInt) owns registered trademarks including (at least five): **ZIEBART®**, **IT’S US. OR RUST®**, **ZEEGARD®**, **ZEE-GLAZE®**, and **FORMULA Z®** [seed:48]. Additional Ziebart trademarks listed include **INNER-CLEAN®**, **TIDY CAR®**, **Z-LINER®**, **Z-SHIELD®**, and **DIAMOND GLOSS®** [seed:50].

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
  - 6ee15a9adda4a5d50f603b3842853ad7 --adjacent--> a84ab6a16afd0ced9230f8d8e3ff5c1b
  - 6ee15a9adda4a5d50f603b3842853ad7 --adjacent--> 9dea3d7cf730cdb2a24504b7332bf68a
  - 6ee15a9adda4a5d50f603b3842853ad7 --adjacent--> 6952d5b23ca401148741ec2bb518c939
  - 6ee15a9adda4a5d50f603b3842853ad7 --adjacent--> e14b0e4c19b915b3e7e2ea7670007afc
  - 6ee15a9adda4a5d50f603b3842853ad7 --adjacent--> a13fa81afe772c557ae10253aac7513a
  - 6ee15a9adda4a5d50f603b3842853ad7 --adjacent--> c5029eb956ea61afae821459fe885f30
  - 6ee15a9adda4a5d50f603b3842853ad7 --adjacent--> 7b1ebbbe031c4486700c4f694d7a89ab

---

### q9: What happens to the franchise upon termination according to the agreement?

**Seeds:** 5 | **Expanded:** 15 | **Edges:** 10 | **Tokens:** 6496

**Query Normalization:**
  - Q0: `What happens to the franchise upon termination according to the agreement?`
  - Q1: `termination agreement happens upon franchise`

**Seed Pages:** [59, 101, 103, 132, 161]

**Seed Sections:** ['Appendix', 'Conclusion', 'Results']

**Evidence Recall:** PASS ✓
  - Reason: Value 'cease' grounded in cited context

**Keywords:** 2/3 matched

**Answer:**

> Upon termination or expiration of the franchise agreement (including a transfer), the franchisee must immediately stop using the licensed trademarks, trade dress, manuals/system materials, and confidential information, and must deliver to the franchisor items bearing the licensed trademarks (including tools, manuals, copyrighted materials, sign faces, and advertising/promotional materials) [seed:101]. The franchisee must also de-identify the location (including equipment and vehicles, such as ch...

**Citations:** 4
  - seed: page 101
  - adjacent: page 102
  - seed: page 103
  - adjacent: page 103

**Expanded Nodes:** 15
  - e45d5e92105ab7c19f48dd369131d2d8 | chunk | page=59 | label=None
  - 2a891fa9b919f62fe5cd555faa66de20 | chunk | page=101 | label=None
  - 5061b1dabc8cde8db907b0f075841cc6 | chunk | page=103 | label=None
  - 333795a47ba3d671d72222a363438dcd | chunk | page=132 | label=None
  - 93c89ac081ec99c1f955370c8358ace9 | chunk | page=161 | label=None
  - 89f8b503fb2c4826ff06019af7476ac3 | chunk | page=58 | label=None
  - c9e7554a593a676f320c59d25ca0da83 | chunk | page=60 | label=None
  - bdb6229c86955fa1fc47123c0ec91639 | chunk | page=102 | label=None
  - ef3614b202949833661cd26ac05d59eb | chunk | page=101 | label=None
  - d4640298404d3d9267cf53d883960363 | chunk | page=102 | label=None

**Edge Trace:** 10
  - 333795a47ba3d671d72222a363438dcd --adjacent--> 89f8b503fb2c4826ff06019af7476ac3
  - 333795a47ba3d671d72222a363438dcd --adjacent--> c9e7554a593a676f320c59d25ca0da83
  - 333795a47ba3d671d72222a363438dcd --adjacent--> bdb6229c86955fa1fc47123c0ec91639
  - 333795a47ba3d671d72222a363438dcd --adjacent--> ef3614b202949833661cd26ac05d59eb
  - 333795a47ba3d671d72222a363438dcd --adjacent--> d4640298404d3d9267cf53d883960363
  - 333795a47ba3d671d72222a363438dcd --adjacent--> ef0c5b025b06571549e28c01b9573bbf
  - 333795a47ba3d671d72222a363438dcd --adjacent--> 614c15678c0f2724b5a0ef005e46c80c
  - 333795a47ba3d671d72222a363438dcd --adjacent--> 0a47f0844f6def5e8931f3c6ace08a53
  - 333795a47ba3d671d72222a363438dcd --adjacent--> 5256127e49782f63c2e08c7c348afaa8
  - 333795a47ba3d671d72222a363438dcd --adjacent--> 9aa5bd4b3497968ad7fdd4579db9f609

---

### q10: What is the address of Ziebart Corporation headquarters?

**Seeds:** 5 | **Expanded:** 12 | **Edges:** 7 | **Tokens:** 4353

**Query Normalization:**
  - Q0: `What is the address of Ziebart Corporation headquarters?`
  - Q1: `address corporation ziebart headquarters the address`

**Seed Pages:** [8, 242, 260, 261]

**Seed Sections:** ['Conclusion', 'Discussion']

**Evidence Recall:** PASS ✓
  - Reason: Value 'Troy' grounded in cited context

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
  - 5f88b2fef750370501bf73b779ee3bd2 --adjacent--> a4e694a19e5ae7488ef7be7df5d53226
  - 5f88b2fef750370501bf73b779ee3bd2 --adjacent--> 596f1f9da21a980c028514fd3754afa9
  - 5f88b2fef750370501bf73b779ee3bd2 --adjacent--> 2fa1d85febec9893c612901850cfab9d
  - 5f88b2fef750370501bf73b779ee3bd2 --adjacent--> cf3585d12e77185af781d098a030cf32
  - 5f88b2fef750370501bf73b779ee3bd2 --adjacent--> 4b9b1dc9d64e5a9327587a3b8cf6a660
  - 5f88b2fef750370501bf73b779ee3bd2 --adjacent--> eb233954d72f93a594f4b51ddb94561f
  - 5f88b2fef750370501bf73b779ee3bd2 --adjacent--> 77f9d685288c9063eb3fdab56fa688b9

---

### q11: What is the opening inventory cost range for a Ziebart franchise?

**Seeds:** 5 | **Expanded:** 11 | **Edges:** 6 | **Tokens:** 4530

**Query Normalization:**
  - Q0: `What is the opening inventory cost range for a Ziebart franchise?`
  - Q1: `inventory cost opening ziebart range`

**Seed Pages:** [15, 16, 25, 26, 82]

**Seed Sections:** ['Conclusion', 'Methodology']

**Evidence Recall:** PASS ✓
  - Reason: Value '32,000' grounded in cited context

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
  - 6d1be3dc0274b75509c6a70082b1f5d6 --adjacent--> f5dde69ad6d2c1b57293d42772b1b05b
  - 6d1be3dc0274b75509c6a70082b1f5d6 --adjacent--> 7df3c3398e958c1a097af6a423dcf94f
  - 6d1be3dc0274b75509c6a70082b1f5d6 --adjacent--> 635f421dffb1df173cd70de2be06f4c4
  - 6d1be3dc0274b75509c6a70082b1f5d6 --adjacent--> d0cdc6be95193fa28cd6173c88eb8976
  - 6d1be3dc0274b75509c6a70082b1f5d6 --adjacent--> 81ae3245f0a5ddce61f04a60f8f40603
  - 6d1be3dc0274b75509c6a70082b1f5d6 --adjacent--> 96b5126cf2df95003987c260647df749

---

### q12: Are there any special provisions for Veterans?

**Seeds:** 5 | **Expanded:** 13 | **Edges:** 8 | **Tokens:** 4482

**Query Normalization:**
  - Q0: `Are there any special provisions for Veterans?`
  - Q1: `there any special provisions any veterans`

**Seed Pages:** [14, 15, 159, 161, 201]

**Seed Sections:** ['Appendix']

**Evidence Recall:** PASS ✓
  - Reason: Value 'veteran' grounded in cited context

**Keywords:** 3/3 matched

**Answer:**

> Yes. Ziebart has a “Veteran Franchise Fee Discount Program” under which it will waive the Initial Franchise Fee for qualified veterans (honorably discharged or currently serving and eligible for an honorable discharge) [seed:14]. Qualified veterans must pay a non-refundable $20,000 Deposit Fee that is credited to the Start-Up Order upon signing the Franchise Agreement [seed:14].  

If a qualified veteran enters into a Development Agreement, the veteran pays a non-refundable Development Fee for a...

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
  - a65bbb958eb66abe442fbd3cb999527f --adjacent--> a1c6de92034e334c558e367fcb0f128f
  - a65bbb958eb66abe442fbd3cb999527f --adjacent--> 0af0d414507af06fc2573b73751c9f24
  - a65bbb958eb66abe442fbd3cb999527f --adjacent--> 907c3d867dc70ca8adc67472a4159547
  - a65bbb958eb66abe442fbd3cb999527f --adjacent--> 87985e1db11dfa37ea7c947e2ba158a4
  - a65bbb958eb66abe442fbd3cb999527f --adjacent--> 0a5a8148557e0e1844a3d694a12c5954
  - a65bbb958eb66abe442fbd3cb999527f --adjacent--> 93c89ac081ec99c1f955370c8358ace9
  - a65bbb958eb66abe442fbd3cb999527f --adjacent--> 39975668459cc8ae2321eae5d82c05ef
  - a65bbb958eb66abe442fbd3cb999527f --adjacent--> 4a0274c225857072f6e67f911a2fc6c9

---

### q13: What is required regarding the warranty program and NALF?

**Seeds:** 5 | **Expanded:** 15 | **Edges:** 10 | **Tokens:** 6130

**Query Normalization:**
  - Q0: `What is required regarding the warranty program and NALF?`
  - Q1: `required nalf warranty regarding program`

**Seed Pages:** [17, 20, 86, 90, 131]

**Seed Sections:** ['Appendix', 'Conclusion']

**Evidence Recall:** PASS ✓
  - Reason: Value 'NALF' grounded in cited context

**Keywords:** 3/3 matched

**Answer:**

> - You must offer certain warranties, and for services warranted under the Ziebart® Trademarks you may only purchase **approved warranties** [seed:20].  
- The warranty program is operated under the **North American Liability Fund (NALF)** and is **self-funded** [seed:20].  
- You are required to **join/participate in NALF** and **issue only the warranties** the franchisor has approved [seed:86].  
- If you offer rustproofing services, you must pay a **premium fee for each rustproofing warranty**...

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
  - Q1: `requirements disclosure state-specific the michigan michigan`

**Seed Pages:** [4, 5, 6, 157, 158]

**Seed Sections:** ['Appendix']

**Evidence Recall:** PASS ✓
  - Reason: Value 'Michigan' grounded in cited context

**Keywords:** 3/3 matched

**Answer:**

> Michigan state-specific disclosures in the provided context include:

- **Notice of prohibited practices / void provisions:** Michigan requires disclosure that certain “unfair provisions” are **void and unenforceable** if included in franchise documents, including (among others) prohibitions on joining a franchisee association; required waivers/releases that deprive statutory rights; termination before term expiration except for “good cause” with notice and up to 30 days to cure; nonrenewal with...

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
  - 097927e5c1dbe4b27047d82b13796227 --adjacent--> 17e6694087eac0440d0dbda4369f4aef
  - 097927e5c1dbe4b27047d82b13796227 --adjacent--> 1ee57f061d780559e29bf149d194903c
  - 097927e5c1dbe4b27047d82b13796227 --adjacent--> a4e694a19e5ae7488ef7be7df5d53226
  - 097927e5c1dbe4b27047d82b13796227 --adjacent--> 456e96c52cb900d34dd060e01ad1dc07
  - 097927e5c1dbe4b27047d82b13796227 --adjacent--> b00663dd46ad6c9ce53e8e79bcb540e9
  - 097927e5c1dbe4b27047d82b13796227 --adjacent--> 88f55c64bc08e00a1f84d019e61d5148

---

### q15: Is there any pending litigation disclosed?

**Seeds:** 5 | **Expanded:** 13 | **Edges:** 8 | **Tokens:** 4159

**Query Normalization:**
  - Q0: `Is there any pending litigation disclosed?`
  - Q1: `there any disclosed litigation any pending`

**Seed Pages:** [13, 164, 199, 256]

**Seed Sections:** ['Appendix', 'Conclusion']

**Evidence Recall:** PASS ✓
  - Reason: Value 'no' grounded in cited context

**Keywords:** 3/3 matched

**Answer:**

> Item 3 states that no litigation is required to be disclosed [seed:13]. The New York addendum further states that neither the Franchisor (nor related persons/entities) has any administrative, criminal, or civil action pending alleging specified violations [seed:164], and repeats the same statement for New York [seed:199].

**Citations:** 3
  - seed: page 13
  - seed: page 164
  - seed: page 199

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
  - 18b25d67ee179a15187b404430fe585e --adjacent--> 415c9d0dc49f0479e99eda4a3e78ff0c
  - 18b25d67ee179a15187b404430fe585e --adjacent--> a1c6de92034e334c558e367fcb0f128f
  - 18b25d67ee179a15187b404430fe585e --adjacent--> 3e6e244ae2c19aff56de75a6e011e6f9
  - 18b25d67ee179a15187b404430fe585e --adjacent--> bdc3efc69e638e871c0afffd7815a6c5
  - 18b25d67ee179a15187b404430fe585e --adjacent--> ad6bc7cd14e25095bac6ee131e65cda0
  - 18b25d67ee179a15187b404430fe585e --adjacent--> 79591579742ec6a83bfc7bb286ea99f7
  - 18b25d67ee179a15187b404430fe585e --adjacent--> 7acbfc1a8f962e331ec88e424692e656
  - 18b25d67ee179a15187b404430fe585e --adjacent--> 1ff09c29eee3160552258c94400ba0fc

---

### q16: What is the training cancellation fee?

**Seeds:** 5 | **Expanded:** 11 | **Edges:** 6 | **Tokens:** 4629

**Query Normalization:**
  - Q0: `What is the training cancellation fee?`
  - Q1: `cancellation training the training fee training cancellation`

**Seed Pages:** [17, 18, 43, 44, 141]

**Seed Sections:** ['Appendix', 'Conclusion']

**Evidence Recall:** PASS ✓
  - Reason: Value '100' grounded in cited context

**Keywords:** 3/3 matched

**Answer:**

> The training cancellation fee is **$100 per occurrence**, plus **any non-refundable airfare** for trips purchased by the trainers, if you cancel training **within 7 days of the scheduled start time** [seed:18].

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
  - 71c74e697cf94c57dd2550029e5fee34 --adjacent--> c4871760f79359a6eedb36d4297ebe82
  - 71c74e697cf94c57dd2550029e5fee34 --adjacent--> 5eebc8f832510c5e221c62c7c33607a4
  - 71c74e697cf94c57dd2550029e5fee34 --adjacent--> a12fad7544a0fe6d56cad7d788e43d60
  - 71c74e697cf94c57dd2550029e5fee34 --adjacent--> f37b54c4b03d24191026fb2239d0f30c
  - 71c74e697cf94c57dd2550029e5fee34 --adjacent--> e0b51fc13745fac1a83c4fc125451e0a
  - 71c74e697cf94c57dd2550029e5fee34 --adjacent--> 877a7d1547925f5b3c04ee11e60a454c

---

### q17: Who is the Vice President of Information Technology at Ziebart?

**Seeds:** 5 | **Expanded:** 11 | **Edges:** 6 | **Tokens:** 3589

**Query Normalization:**
  - Q0: `Who is the Vice President of Information Technology at Ziebart?`
  - Q1: `vice technology ziebart president information`

**Seed Pages:** [8, 11, 12, 261]

**Seed Sections:** ['Conclusion']

**Evidence Recall:** PASS ✓
  - Reason: Value 'Stewart' grounded in cited context

**Keywords:** 3/3 matched

**Answer:**

> Larry Stewart is the Vice President of Information Technology at Ziebart (Ziebart International Corporation/ZInt) [seed:12].

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
  - Q1: `linings relationship ziebart the rhino rhino`

**Seed Pages:** [8, 52, 53, 124, 136]

**Seed Sections:** ['Appendix', 'Conclusion']

**Evidence Recall:** PASS ✓
  - Reason: Value 'Rhino' grounded in cited context

**Keywords:** 3/3 matched

**Answer:**

> Rhino Linings Corporation (“Rhino”) has a supplier/development relationship with Ziebart (through Ziebart International Corporation (“ZInt”) and Ziebart Corporation (“ZC”)) under which Rhino grants Ziebart a limited exclusive right to sublicense Ziebart® franchisees to sell and apply Rhino® bed liner coatings (“Rhino® Coatings”) and to use the Rhino trademarks (“Rhino Marks”) in approved market areas. This is done via a Development Agreement (restated June 15, 2009; renewed March 27, 2025; five-...

**Citations:** 4
  - seed: page 53
  - adjacent: page 9
  - seed: page 124
  - seed: page 136

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
  - Q1: `washington the provisions state franchisees provisions`

**Seed Pages:** [161, 162, 201]

**Seed Sections:** ['Appendix']

**Evidence Recall:** PASS ✓
  - Reason: Value 'Washington' grounded in cited context

**Keywords:** 3/3 matched

**Answer:**

> For Washington state franchisees, **Addendum S (Washington Franchise Agreement and Multi-Unit Development Agreement Addendum)** provides (and may modify the FDD, franchise agreement, and related agreements) the following key provisions: it applies if the offer is accepted in Washington, the purchaser is a Washington resident, and/or the franchised business is located/operated wholly or partly in Washington [seed:161].

- **Conflict of laws:** If there is a conflict of laws, the **Washington Fran...

**Citations:** 2
  - seed: page 161
  - seed: page 162

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

**Seeds:** 5 | **Expanded:** 14 | **Edges:** 9 | **Tokens:** 5213

**Query Normalization:**
  - Q0: `What is the environmental compliance policy for Ziebart franchises?`
  - Q1: `franchises compliance ziebart environmental policy`

**Seed Pages:** [1, 10, 38, 80, 89]

**Seed Sections:** ['Conclusion', 'Methodology']

**Evidence Recall:** PASS ✓
  - Reason: Value 'not' grounded in cited context

**Answer:**

> Ziebart’s disclosure document states that there are **no industry-specific regulations** for Ziebart franchises, but franchisees **must become familiar with federal and state laws and regulations for the proper handling of chemicals and hazardous substances** [seed:10]. It also notes that Ziebart franchises are subject to **various federal, state, and local government regulations** (in addition to general business laws), including regulations related to **site location and building construction*...

**Citations:** 1
  - seed: page 10

**Expanded Nodes:** 14
  - eff3c75d1a170c94bce6d7e071002013 | chunk | page=1 | label=None
  - 2754d667481fcc3354cca13a4c020570 | chunk | page=10 | label=None
  - 38614ad713981b9cc6406db565ad1412 | chunk | page=38 | label=None
  - 2c16e3855421cba31878963d8e5653a8 | chunk | page=80 | label=None
  - fedde5a4e97fb8c4638546b27b9082c6 | chunk | page=89 | label=None
  - 1ed976f1656f89ad3537308ebc19e11c | chunk | page=1 | label=None
  - 50c611560e036741a8d4cb10cd5fc66c | chunk | page=9 | label=None
  - 956fa4aeaeecdc8b3788ca927faa6017 | chunk | page=11 | label=None
  - 71d97383dc7bf5e4ce8c9f8ab62505b8 | chunk | page=37 | label=None
  - fbd3c936ecf93d69469e034c71fa2d1d | chunk | page=38 | label=None

**Edge Trace:** 9
  - 2c16e3855421cba31878963d8e5653a8 --adjacent--> 1ed976f1656f89ad3537308ebc19e11c
  - 2c16e3855421cba31878963d8e5653a8 --adjacent--> 50c611560e036741a8d4cb10cd5fc66c
  - 2c16e3855421cba31878963d8e5653a8 --adjacent--> 956fa4aeaeecdc8b3788ca927faa6017
  - 2c16e3855421cba31878963d8e5653a8 --adjacent--> 71d97383dc7bf5e4ce8c9f8ab62505b8
  - 2c16e3855421cba31878963d8e5653a8 --adjacent--> fbd3c936ecf93d69469e034c71fa2d1d
  - 2c16e3855421cba31878963d8e5653a8 --adjacent--> fadec2c0e091efbfbd3bc6d496704d79
  - 2c16e3855421cba31878963d8e5653a8 --adjacent--> 24274037191731e953b1b205aaa03462
  - 2c16e3855421cba31878963d8e5653a8 --adjacent--> 5a9b0d3dc20900533bc8de28eaa9c603
  - 2c16e3855421cba31878963d8e5653a8 --adjacent--> 91993c1f981b4973a0f1a012f408d275

---

# NPR — Near-Perfect RAG

## End-to-End Lighthouse Specification + Contracts + Acceptance Gates

**Version:** 1.0 (Lighthouse / Source of Truth)
**Status:** Implementation-ready design spec (research-backed, no vendor lock)
**Audience:** Principal engineer + AI engineer building the full system
**Goal:** If the corpus contains the answer → retrieve the correct evidence and answer grounded with citations. If not → abstain or ask targeted clarifying questions. Never guess.

---

## 0) Non-Negotiables

1. **Evidence-first:** generation can only use evidence spans from the corpus (EvidencePack).
2. **Claim-citation completeness:** every factual claim must have ≥1 citation span (doc_id + version_id + offsets).
3. **Answerability:** if insufficient evidence, **ASK_CLARIFYING** or **ABSTAIN**.
4. **Conflict handling:** detect contradictions; apply explicit source-of-truth policy; optionally present conflicts with citations.
5. **Planner-first:** system consults corpus meta-knowledge and constraints before retrieval.
6. **Reproducibility:** every response must produce a replayable trace (“flight recorder”).
7. **Quality gates:** no phase can be marked done without passing defined evaluation thresholds.

---

## 1) Definitions

* **Corpus:** all ingested sources (files, pages, tickets, DB rows, etc.).
* **DocumentIR:** canonical structured representation of a document (layout/sections/tables/offset map).
* **Chunk:** retrieval unit created from DocumentIR with structure-aware logic.
* **EvidenceSpan:** extractive span from a chunk with offsets for citations.
* **EvidencePack:** curated, compressed, deduplicated set of EvidenceSpans for generation.
* **Meta-Knowledge:** corpus catalog + taxonomy + acronym dictionary + entity/doc graph + coverage stats + quality signals.
* **RetrievalPlan:** structured plan specifying which retrieval modalities to use, filters, budgets, and stop conditions.
* **Near-Perfect:** extremely high retrieval recall and precision when answer exists + stable, grounded generation; explicit abstention otherwise.

---

## 2) System Overview

The system is split into **OFFLINE** and **ONLINE** planes.

### OFFLINE: Ingestion & Index Build

1. Connectors pull sources → versioning + canonical IDs
2. Parse & normalize → **DocumentIR**
3. Security tagging (PII/secrets/injection risk) → *tag/filter strategy*
4. Metadata extraction (rules + NER + optional LLM)
5. Structure-aware chunking + special handling for tables/code/figures
6. Build retrieval indices:

   * Dense vector index (single-vector)
   * Sparse lexical index (BM25/BM25F)
   * Neural sparse (optional)
   * Late-interaction / multi-vector (optional but supported)
   * Graph index (entity + document graphs)
   * Structured store (SQL) for normalized facts + catalog
   * Multimodal index (optional but first-class if PDFs/images)
7. Build Meta-Knowledge layer artifacts
8. Build/refresh evaluation sets (golden + synthetic optional)

### ONLINE: Query → Plan → Retrieve → Fuse → Rerank → EvidencePack → Decide → Generate → Verify → Respond

1. Input gateway & context assembly
2. Planner produces RetrievalPlan DSL
3. Execute plan (parallel, multi-modal)
4. Candidate fusion + rerank
5. EvidencePack build (extractive compression, stable ordering)
6. Answerability + contradiction decision
7. Generation (structured claims + citations)
8. Verification gate (claim checks)
9. Corrective retrieval loop (if needed)
10. Output + trace logging

---

## 3) Canonical Data Model (Contracts)

These are **immutable** contracts. Any change increments `schema_version`.

### 3.1 DocumentRef

```json
{
  "schema_version": "1.0",
  "doc_id": "string",
  "version_id": "string",
  "source_type": "pdf|docx|pptx|html|md|txt|csv|xlsx|wiki|ticket|email|db|image",
  "source_uri": "string",
  "mime_type": "string",
  "checksum": "string",
  "created_at": "ISO-8601|null",
  "modified_at": "ISO-8601|null",
  "owner": "string|null",
  "team": "string|null",
  "acl": { "labels": ["string"], "principals": ["string"] }
}
```

### 3.2 DocumentIR (Canonical)

Must preserve structure + offsets + provenance mappings.

```json
{
  "schema_version": "1.0",
  "doc_ref": { "...DocumentRef" },
  "title": "string|null",
  "language": "string|null",
  "pages": [
    {
      "page_num": 1,
      "blocks": [
        { "type": "heading|paragraph|table|figure|code|list", "text": "string|null",
          "cells": "table-cells|null", "bbox": "optional", "start_offset": 0, "end_offset": 123 }
      ]
    }
  ],
  "sections": [
    { "section_id": "string", "heading": "string", "level": 1,
      "block_refs": ["opaque pointers"], "section_path": ["string"] }
  ],
  "offset_map": "opaque mapping enabling citations to raw artifact",
  "quality": {
    "parse_confidence": 0.0,
    "ocr_used": true,
    "ocr_confidence": 0.0,
    "table_confidence": 0.0
  }
}
```

### 3.3 ChunkRef + ChunkRecord

```json
{
  "schema_version": "1.0",
  "chunk_ref": {
    "chunk_id": "string",
    "doc_id": "string",
    "version_id": "string",
    "section_path": ["string"],
    "chunk_type": "text|table|code|figure_caption|image_region",
    "start_offset": 123,
    "end_offset": 456
  },
  "fields": {
    "title": "string|null",
    "heading_context": "string|null",
    "body": "string",
    "table_struct": "optional",
    "code_lang": "optional",
    "entities_str": "string|null",
    "context_str": "string|null"
  },
  "metadata": {
    "doc_type": "policy|spec|runbook|ticket|email|other",
    "products": ["string"],
    "components": ["string"],
    "time_range": { "start": "ISO-8601|null", "end": "ISO-8601|null" },
    "version_tags": ["string"],
    "topics": ["string"],
    "entities": [{ "type": "string", "id": "string|null", "name": "string", "confidence": 0.0 }],
    "authority_tier": "TIER_1|TIER_2|TIER_3",
    "recency_score": 0.0,
    "injection_risk_score": 0.0,
    "pii_present": true,
    "secrets_present": true
  }
}
```

### 3.4 EvidenceSpan + EvidencePack

```json
{
  "schema_version": "1.0",
  "evidence_pack": {
    "pack_id": "string",
    "query_hash": "string",
    "items": [
      {
        "chunk_ref": { "...ChunkRef" },
        "source_uri": "string",
        "spans": [
          { "start_offset": 123, "end_offset": 200, "text": "string" }
        ],
        "scores": { "final": 0.0, "dense": 0.0, "sparse": 0.0, "graph": 0.0, "late": 0.0 },
        "trust": { "authority_tier": "TIER_1", "authority": 0.0, "recency": 0.0 },
        "why_included": { "signals": ["term_overlap", "entity_match", "graph_path"], "notes": "string|null" }
      }
    ],
    "coverage": {
      "entities_covered": ["string"],
      "time_coverage": "full|partial|none",
      "constraints_satisfied": ["string"],
      "missing_constraints": ["string"]
    },
    "ordering_policy": "authority_then_relevance_then_recency",
    "normalization_format_id": "evidence_format_v1"
  }
}
```

---

## 4) OFFLINE PLANE — Required Components + Tests

### 4.1 Connectors

**Responsibilities**

* Pull documents, assign stable `doc_id`, monotonic `version_id`
* Incremental updates (delta sync)
* Store raw artifacts in object store

**Gates**

* Idempotency: ingest same doc/version twice ⇒ no duplicates
* Version graph correctness: update creates new `version_id`, links to previous

### 4.2 Parsing & Normalization (DocumentIR)

**Responsibilities**

* Layout-aware parsing for PDFs
* Preserve section hierarchy and tables
* OCR for scans with confidence scoring
* Offset map for citations

**Gates**

* Parse coverage ≥ target threshold on validation set
* Table extraction spot-check pass rate ≥ threshold
* OCR confidence tracked; low OCR docs flagged for special handling

### 4.3 Security/PII/Injection Tagging (Tag > Delete)

**Responsibilities**

* Tag PII/secrets (optionally redact secrets)
* Compute `injection_risk_score`
* Do NOT allow doc text to override system policies

**Gates**

* Secrets detection false-negative rate below threshold (if enforced)
* Injection strings never influence system prompt or output behavior (tested)

### 4.4 Metadata Extraction (Rules + NER + Optional LLM)

**Responsibilities**

* Catalog metadata: doc_type, product/component, time range, version tags, owner/team
* Semantic metadata: entities, topics, acronyms
* Authority tier assignment + recency scoring
* Optional: synthetic questions (planner-only artifact)

**Gates**

* Metadata completeness for required fields ≥ threshold
* Entity linking precision/recall tracked on labeled subset

### 4.5 Chunking / Segmentation (Structure-aware)

**Responsibilities**

* Maintain section context in chunk headers
* Special handling:

  * tables stored as structured + textual representation
  * code as code chunk + optional explanation chunk
  * figures: captions + references preserved; optional region extraction
* Produce `context_str` to enable contextual retrieval

**Gates**

* No mixed-unrelated-sections in chunks
* Chunk context includes section path and heading summary
* Chunk token distribution within configured bounds

---

## 5) RETRIEVAL INDICES — “Near-Perfect Vector Search” and Beyond

### 5.1 Embedding Strategy (Mandatory Spec)

**We do not use a single embedding. We use an embedding stack.**

#### 5.1.1 Embedding Views per Chunk (Multi-View)

For each chunk, store vectors for:

1. `vec_content` = body text
2. `vec_contextual` = **contextualized** content (prepend structured context: title, section path, key metadata, entity string)
3. `vec_title_heading` = title + headings
4. `vec_entities` = canonical entities string
5. Optional `vec_doc_summary` = doc summary (planner/routing use; not answer text)

**Contract**

* Every vector stores: `embedding_model_id`, `dim`, `normalize=true/false`, `created_at`, `input_template_id`

#### 5.1.2 Query vs Document Embedding Templates

Define explicit templates:

* Query template: includes query + extracted constraints (time/product/version)
* Doc template: includes chunk + context header

#### 5.1.3 Model Selection Protocol (No Lock-In)

We maintain a benchmark harness that can swap candidates:

* Dense single-vector model(s)
* Late-interaction / multi-vector model(s)
* Neural sparse model(s)

**Gate**

* A model is “eligible” only if it improves retrieval metrics on our golden set under fixed budgets.

### 5.2 Dense Vector Index

**Responsibilities**

* Store multi-view vectors with metadata filters
* Support “narrow-then-search” (preferred) and “search-with-filters” (measured)

### 5.3 ANN Correctness Gates (Mandatory)

We must prove ANN isn’t silently dropping recall.

**Requirements**

* Maintain an **Exact kNN comparator** (on sampled subsets or narrowed slices)
* Report:

  * `ANN_recall@k` vs exact kNN for representative query sets
  * `Filtered_ANN_recall@k` separately
  * Sensitivity tests (reindex order, incremental updates, distribution shift)

**Gate**

* ANN config cannot ship unless recall gates meet thresholds.
* If filtered recall degrades, planner must prefer **metadata narrowing first**, then search within the narrowed subset (or exact search in subset).

### 5.4 Sparse Lexical Index (BM25/BM25F)

**Responsibilities**

* Fielded indexing: title/headings boosted (BM25F ideal)
* Exact-token fields for IDs/error codes
* Analyzers for synonyms/acronyms dictionary (controlled)

### 5.5 Neural Sparse (Optional but First-Class)

* Learned sparse retriever integrated into fusion pipeline
* Used when vocabulary mismatch is common

### 5.6 Late Interaction / Multi-Vector (Precision Escalator)

**Use**

* When answerability confidence is low OR top candidates are near-duplicates OR query needs pinpoint span retrieval

**Budget**

* Only run on top-N candidates to control cost

### 5.7 Graph Index (Entity + Document)

**Entity Graph**

* canonical entities + aliases + relationships

**Document Graph**

* cites, supersedes, duplicates, contradicts, derived_from, same_topic

**Graph Discipline Policy (Mandatory)**

* Graph retrieval is invoked only when planner flags multi-hop / entity-relational / cross-doc dependency.
* Otherwise graph is skipped to avoid noise.

**Query-Built Evidence Graph (Optional but Supported)**

* For complex queries, system may build a temporary evidence graph from retrieved candidates to reduce KG incompleteness.

### 5.8 Structured Store (SQL)

For normalized facts, catalog metadata, coverage stats, policy tiers, etc.

### 5.9 Multimodal Retrieval (If corpus includes visual PDFs/images)

* Image/region embeddings
* Layout anchors linking regions ↔ DocumentIR blocks ↔ chunks
* Planner routes to multimodal when query references figures/tables/visual cues or when doc type is “visual-heavy”

---

## 6) ONLINE PLANE — Components + Contracts

### 6.1 Input Gateway

**Responsibilities**

* Normalize input, language detect
* Intent classification (QA, compare, troubleshoot, summarize, etc.)
* Constraint extraction (time/product/version/env)
* Typos/ID normalization (do-not-silently-change; propose corrections explicitly)
* Injection detection for user input (ignore attempts to override policy)

**Output:** `QueryContext`

### 6.2 Planner (RetrievalPlan DSL) — Key Component

**Inputs**

* QueryContext
* Meta-Knowledge snapshot (catalog, acronyms, coverage stats, likely products)
* Policies (authority tiers, recency preferences, allowed sources)

**Outputs**

* Decision: `PROCEED` or `ASK_CLARIFYING`
* RetrievalPlan JSON (strict schema; deterministic-ish settings)

**Planner Responsibilities**

1. Interpret query: entities, constraints, ambiguity
2. Decide clarification vs proceed
3. Choose modalities: dense/sparse/neural sparse/late/graph/sql/multimodal
4. Choose filters: doc_type, authority tier, time/version/product/component
5. Budgets: top_k per retriever, rerank_n, evidence budget, iterations
6. Define stop conditions and escalation triggers (late-interaction, graph expansion, PRF)

### 6.3 Retrieval Orchestrator

Executes steps in parallel; returns candidate list with provenance and per-retriever scores.

### 6.4 Fusion + Reranking

**Fusion**

* RRF baseline required
* Optional learned fusion later (LTR)

**Reranking**

* Cross-encoder / LLM reranker / LTR (policy-driven)
* Diversity constraints: prevent same-section duplication unless required

### 6.5 EvidencePack Builder (Extractive + Stable)

**Non-negotiables**

* Extractive spans preserved (abstractive is optional but cannot replace raw spans)
* Dedup near-duplicates
* Stable ordering policy
* Context normalization format (deterministic separators + headers)

**Stability Mitigation (Mandatory Test + Optional Runtime)**

* Test suite must measure permutation sensitivity
* Runtime option: for high-stakes, probe small permutations or multi-pack and choose most consistent verified output

### 6.6 Answerability + Contradiction Engine

Outputs decision:

* `ANSWER`
* `ASK_CLARIFYING`
* `ABSTAIN_NO_EVIDENCE`
* `ANSWER_WITH_CONFLICTS`

**Checks**

* Evidence sufficiency
* Constraint satisfaction (time/version/product)
* Contradiction detection (policy-guided resolution)
* Injection-risk handling (require corroboration, downrank)

### 6.7 Answer Generation (Structured First)

**Input**

* QueryContext
* Decision
* EvidencePack
* Output schema

**Output must include**

* `final_text`
* `claims[]` each with citations
* `followups[]`
* `mode` + `confidence`

### 6.8 Verification Gate + Corrective Loop

**Verifier**

* Every claim must map to ≥1 EvidenceSpan
* If fail: produce `repair_plan` (plan deltas)

**Corrective Loop**

* Apply deltas: add phrase query, expand graph, increase top_k, add modality, tighten filters, invoke late interaction
* Stop conditions: max iterations, budget reached, or still insufficient → abstain

---

## 7) Meta-Knowledge Layer (Planner Map of the Territory)

Stored in SQL/graph; used by planner; not used as answer text.

**Artifacts**

* Corpus catalog: sources, coverage by year/product/component/team
* Taxonomy/ontology
* Acronym dictionary
* Topic clusters
* Quality signals: authority tier, recency, completeness, reliability
* Optional synthetic queries per doc/section
* Document lineage and version supersession map

**Gates**

* Catalog refresh correctness and versioning
* Coverage statistics must be consistent with index contents

---

## 8) Flight Recorder (Mandatory)

Every query produces a replayable trace object:

**Trace includes**

* QueryContext
* Meta-Knowledge snapshot hash/version
* RetrievalPlan (exact)
* Retriever outputs (candidates with scores)
* Fusion + rerank output
* EvidencePack
* Answerability decision + rationale signals
* Draft answer (claims)
* Verification results
* Any corrective loops (plan deltas)
* Final response

**Requirement**

* Deterministic replay must reproduce the same pipeline decisions (except nondeterministic model outputs; those are captured with model versions + prompts + seeds where available).

---

## 9) Evaluation & Benchmarking (Mandatory)

### 9.1 Golden Set Schema

Each record contains:

* query_text
* constraints (time/product/version/env)
* label: answerable / ambiguous / unanswerable / conflicting
* expected_doc_ids
* expected_spans (optional but ideal)
* expected_behavior (clarifying questions, abstain, conflict presentation)

### 9.2 Metrics (Hard Requirements)

**Retrieval**

* Recall@K (doc_id match)
* nDCG@K, MRR
* Filtered recall@K
* ANN recall@K vs exact kNN comparator

**Answer Quality**

* Claim citation coverage (must be 100% for supported claims)
* Faithfulness / groundedness (no unsupported claims)
* Conflict handling correctness on conflict set

**Abstention**

* False answer rate (must be near zero)
* Abstain precision/recall on unanswerable set

**Robustness**

* Injection resistance test pass rate
* Stability under permutation and format changes

### 9.3 Baselines (Required Comparisons)

1. Dense-only
2. Dense + rerank
3. Dense + sparse fusion
4. Full system (planner + graph + verifier + loop)

All run on same golden set and fixed budgets.

---

## 10) Implementation Roadmap (Phased with Gates)

**Phase 0 — Skeleton + Eval Harness (Must First)**

* Schemas + storage
* Ingest → parse → chunk
* Dense + sparse retrieval + evidence pack + answer with citations
* Basic abstain if insufficient evidence
  **Gate:** golden set runner works; trace logging works; claim-citation completeness enforced

**Phase 1 — Fusion + Dedup + Evidence Normalization**

* RRF fusion
* EvidencePack stable ordering + normalization format
  **Gate:** measurable recall improvement; stability tests baseline captured

**Phase 2 — Planner v1 + Metadata Narrowing**

* Rules-based planner
* Metadata-first narrowing before vector search
  **Gate:** ambiguous queries correctly ask clarifying; filtered retrieval doesn’t reduce recall

**Phase 3 — ANN Recall Gates + Exact Comparator**

* ANN tuning harness + exact kNN comparator
* Publish ANN recall gates
  **Gate:** ANN recall thresholds satisfied (including filtered recall)

**Phase 4 — Graph + Authority + Conflicts**

* Entity extraction + doc graph
* Conflict resolution policy implemented
  **Gate:** conflict test set passes (correct prioritization and/or conflict display)

**Phase 5 — Verification + Corrective Retrieval Loop**

* Claim verifier
* Plan deltas and retry loop
  **Gate:** hallucination rate (unsupported claims) approaches zero on eval

**Phase 6 — Precision Escalators**

* Late interaction / multi-vector on top-N
* Neural sparse integration (optional)
  **Gate:** improved pinpoint accuracy and reduced misses on hard subset

**Phase 7 — Multimodal (If Needed)**

* Region embeddings + layout anchors + multimodal planner branch
  **Gate:** improves performance on visual-heavy docs without harming others

---

## 11) Configuration Knobs (Explicit)

* chunk token targets/min/max/overlap
* contextual embedding header template IDs
* embedding models and dimensions (full vs truncated)
* top_k per retriever; rerank_n
* fusion method and parameters
* evidence budget (items/tokens/spans per chunk)
* max corrective iterations
* authority tier policy and recency weighting
* stability mitigation settings (test-only vs runtime probe)
* ANN index params (e.g., HNSW efConstruction/efSearch/M or equivalents)

---

## 12) Explicit Policies (Must be Written, Not Implied)

* **Source of truth tiers** (what outranks what; how recency interacts)
* **Conflict policy** (resolve vs present vs ask clarifying)
* **Corroboration policy** (when one source is enough vs require two)
* **Clarifying question policy** (max 1–3 questions; targeted; only when materially affects retrieval)
* **Abstention policy** (what to say; how to suggest next steps without guessing)

---

## 13) Deliverables Checklist (Nothing Missing)

To declare “lighthouse complete,” we must have:

* ✅ Canonical schemas (DocumentRef, DocumentIR, ChunkRecord, EvidencePack, RetrievalPlan, Trace)
* ✅ Offline pipeline spec + quality gates
* ✅ Index strategy spec (dense, sparse, optional neural sparse, late interaction, graph, structured, multimodal)
* ✅ Embedding strategy spec (multi-view + contextual templates + versioning)
* ✅ ANN recall gates + exact comparator plan
* ✅ Online pipeline spec (planner → retrieval → fusion → rerank → evidence → answerability → generation → verification → loop)
* ✅ Stability test suite spec (order + formatting)
* ✅ Flight recorder trace spec (replayable)
* ✅ Evaluation harness spec (golden set + baselines + metrics)
* ✅ Phase roadmap with acceptance gates
* ✅ Explicit policies (authority/conflicts/abstain/clarify/corroborate)

If any checkbox is not met, the lighthouse is not complete.

---


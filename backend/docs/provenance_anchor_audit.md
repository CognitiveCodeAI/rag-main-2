# Provenance/Anchoring Audit Report

**Date:** 2026-01-29  
**Objective:** Determine what source provenance anchors exist to support "click citation → open doc → jump to location → highlight"

---

## Executive Summary

**Can a client click a citation and reliably locate the exact source span?**

**Current Answer: Partially — Page-level only**

- ✅ `page_no` is available and populated
- ❌ No bbox for chunks (only figures/tables)
- ❌ No anchor snippet with hash for text search fallback
- ❌ No raw document download endpoint
- ❌ `doc_id` not included in citation response (must infer from request)

**Highlighting Priority Status:**
1. **bbox highlight:** Only available for figures/tables, NOT for text chunks
2. **snippet search fallback:** `text_plain` exists in DB but not returned in citations
3. **page-only jump:** ✅ Supported (page_no always present for chunks)

---

## Audit Findings

### A) Citation Generation

#### Where citations are generated:
| File | Role |
|------|------|
| `app/llm/openai_client.py` | Defines `Citation` dataclass, `_extract_citations()` parses LLM output |
| `app/qa/runner.py:1178-1184` | Converts Citation objects to response dicts |
| `app/routes/qa.py` | `AskResponse` model (untyped `citations: list`) |

#### Current citation payload schema:
```python
# From runner.py line 1178-1184
{
    "node_id": str,   # ✅ Present, populated
    "page_no": int,   # ✅ Present, populated  
    "label": str      # ✅ Present, populated (figures/tables only)
}
```

#### Citation dataclass (openai_client.py):
```python
@dataclass
class Citation:
    node_id: str
    page_no: Optional[int] = None
    label: Optional[str] = None
    text_snippet: Optional[str] = None  # ⚠️ EXISTS but NOT populated
```

**Gap:** `text_snippet` field exists but is never populated during citation extraction.

---

### B) Document-Location Data in Postgres

#### Schema: `nodes` table (graph_models.py)

| Column | Type | Populated? | Notes |
|--------|------|------------|-------|
| `node_id` | String(64) | ✅ Always | Primary key |
| `doc_id` | String(64) | ✅ Always | FK to documents_graph |
| `version` | Integer | ✅ Always | Document version |
| `page_no` | Integer | ✅ Always (chunks) | Nullable but constrained for chunks |
| `chunk_index_in_page` | Integer | ✅ Chunks | Order within page |
| `label` | String(128) | ✅ Figures/tables | e.g., "Figure 1", "Table 2" |
| `text_md` | Text | ✅ Always | Markdown content |
| `text_plain` | Text | ✅ Always | Plain text content |
| `bbox` | JSONB | ⚠️ **Figures/tables only** | `{x0, y0, x1, y1}` |
| `content_hash` | String(64) | ✅ Always | SHA256 of content |
| `meta` | JSONB | ⚠️ Sparse | Varies by node type |

**Critical Finding:** `bbox` field EXISTS in schema but is **explicitly set to `None` for chunks**:

```python
# nodes.py line 61
node = Node(
    ...
    bbox=None,  # <-- Chunks never get bbox!
    ...
)
```

#### Schema: `documents_graph` table

| Column | Populated? | Notes |
|--------|------------|-------|
| `doc_id` | ✅ | Primary key |
| `source_uri` | ✅ | Original file path/URL |
| `content_hash` | ✅ | For deduplication |
| `version` | ✅ | Incrementing version |
| `canonical_doc_id` | ✅ | Content identity linking |
| `embedded_collection_version` | ✅ | Which Milvus collection |

---

### C) API Response Fields

#### `/v1/qa/ask` Response Structure

**`seed_nodes` array:**
```python
{
    "node_id": str,        # ✅
    "score": float,        # ✅
    "page_no": int,        # ✅
    "node_type": str,      # ✅
    "label": str,          # ✅ (figures/tables)
    "section_hint": str,   # ✅
    "text_preview": str    # ✅ (first N chars)
}
# Missing: doc_id, bbox, source_uri
```

**`expanded_nodes` array:**
```python
{
    "node_id": str,        # ✅
    "node_type": str,      # ✅
    "page_no": int,        # ✅
    "label": str,          # ✅
    "text_preview": str,   # ✅
    "expansion_type": str  # ✅ (seed/adjacent/referenced/explained_by)
}
# Missing: doc_id, bbox, source_uri
```

**`citations` array:**
```python
{
    "node_id": str,   # ✅
    "page_no": int,   # ✅
    "label": str      # ✅ (figures/tables)
}
# Missing: doc_id, version, bbox, text_snippet, source_uri
```

**Note:** There's a SEPARATE `Citation` class in `context_packer.py` that DOES include `doc_id` and `bbox`, but this is only used internally for context formatting — not exposed to API clients.

---

### D) Raw Document Access Path

#### MinIO Storage Layout
```
npr-corpus/
├── raw/{doc_id}/{version_id}/original     # Raw uploaded file
├── ir/{doc_id}/{version_id}/document_ir.json
├── chunks/{doc_id}/{version_id}/chunks.jsonl
└── embeddings/{doc_id}/{version_id}/bundle.json
```

#### Storage Client Methods
| Method | Exists? | HTTP Route? |
|--------|---------|-------------|
| `put_raw()` | ✅ | N/A (internal) |
| `get_raw()` | ✅ | ❌ **NO ENDPOINT** |
| `presign_url()` | ❌ | N/A |

**Critical Gap:** No HTTP endpoint exists to download/stream raw documents. Client cannot retrieve the original PDF to render and highlight.

#### Current `source_uri` format:
```
file://C:\Apps\rag\2025 FDD.pdf     # Local file path
upload://{filename}                  # Upload reference
```

Neither format is directly usable by web clients.

---

### E) Bbox Coordinate Conventions

#### For Figures/Tables (where bbox IS populated):

**Source:** PyMuPDF `fitz.Rect` via `figure_detector.py`

```python
bbox = {
    'x0': rect.x0,  # Left edge
    'y0': rect.y0,  # Top edge
    'x1': rect.x1,  # Right edge  
    'y1': rect.y1   # Bottom edge
}
```

| Property | Value |
|----------|-------|
| Origin | Top-left of page |
| Units | PDF points (1/72 inch) |
| Coordinate system | PyMuPDF normalized |
| Page size captured? | ❌ NO |
| Page rotation captured? | ❌ NO |

**Gap:** Without page dimensions and rotation, client cannot reliably map bbox to rendered PDF coordinates.

#### For Chunks:
**Status:** `bbox=None` — **NOT POPULATED**

Chunks are created from text extraction, and the bbox is explicitly not captured:
```python
# nodes.py line 50-64
node = Node(
    ...
    bbox=None,  # Explicitly null
    ...
)
```

---

## Gap Analysis Summary

### What Exists vs What's Needed

| Capability | Schema Exists | Populated | In API Response | Needed for Anchoring |
|------------|---------------|-----------|-----------------|---------------------|
| `doc_id` | ✅ | ✅ | ❌ (not in citations) | ✅ Required |
| `version_id` | ✅ | ✅ | ❌ | ✅ Required |
| `node_id` | ✅ | ✅ | ✅ | ✅ Required |
| `page_no` | ✅ | ✅ | ✅ | ✅ Required |
| `bbox` (chunks) | ✅ | ❌ **NULL** | N/A | ✅ Ideal |
| `bbox` (figures) | ✅ | ✅ | ❌ | ✅ Ideal |
| `anchor_snippet` | ❌ | N/A | N/A | ✅ Fallback |
| `snippet_hash` | ❌ | N/A | N/A | ⚪ Nice-to-have |
| `source_uri` | ✅ | ✅ | ❌ | ✅ Required |
| Raw doc endpoint | N/A | N/A | ❌ **MISSING** | ✅ Required |
| Page dimensions | ❌ | N/A | N/A | ✅ For bbox |
| Page rotation | ❌ | N/A | N/A | ⚪ Edge case |

---

## Example Payloads

### Today's Citation Response
```json
{
  "citations": [
    {
      "node_id": "abc123def456",
      "page_no": 14,
      "label": null
    }
  ]
}
```

### Needed Citation Response (for full anchoring)
```json
{
  "citations": [
    {
      "node_id": "abc123def456",
      "doc_id": "37660ee55b1fb2aa63579e3aeb2aca97",
      "version": 1,
      "page_no": 14,
      "label": null,
      "bbox": {"x0": 72, "y0": 150, "x1": 540, "y1": 200},
      "anchor_snippet": "The initial franchise fee is $45,000",
      "snippet_hash": "a1b2c3d4",
      "source_uri": "/api/v1/documents/{doc_id}/raw"
    }
  ],
  "document_access": {
    "raw_url": "/api/v1/documents/37660ee55b1fb2aa63579e3aeb2aca97/raw",
    "page_dimensions": {"14": {"width": 612, "height": 792}}
  }
}
```

---

## Minimal Next Steps (DO NOT IMPLEMENT YET)

### Priority 1: Enable Page-Jump (Low Effort)
1. Add `doc_id` and `version` to citation response
2. Create `/v1/documents/{doc_id}/raw` endpoint to serve PDF bytes

### Priority 2: Enable Text Search Fallback (Medium Effort)
1. Add `anchor_snippet` to Citation dataclass (first 100 chars of cited text)
2. Populate from `text_plain` during citation extraction
3. Return in API response

### Priority 3: Enable Bbox Highlighting (Higher Effort)
1. Capture bbox during chunk extraction (requires PDF parsing changes)
2. Capture page dimensions alongside bbox
3. Return bbox in expanded_nodes and citations
4. For figures/tables: already have bbox, just need to expose it

### Priority 4: Coordinate Normalization
1. Store page width/height/rotation with bbox
2. Normalize to percentage-based coordinates for client rendering

---

## Files Audited

| File | Purpose |
|------|---------|
| `app/routes/qa.py` | AskResponse model, endpoint |
| `app/qa/runner.py` | QAResult dataclass, citation serialization |
| `app/llm/openai_client.py` | Citation extraction from LLM |
| `app/db/graph_models.py` | Node/Edge/DocumentGraph schemas |
| `app/graph/nodes.py` | Node creation (bbox=None for chunks) |
| `app/graph/figure_detector.py` | Bbox extraction for figures |
| `app/graph/context_packer.py` | Internal Citation with bbox |
| `app/storage/minio_client.py` | Raw document storage |
| `app/routes/documents.py` | Document list/detail (no download) |

---

## Conclusion

The system has **partial provenance support**:
- Page-level jumping is possible today
- Bbox highlighting is only possible for figures/tables
- Text chunk highlighting requires either bbox capture during ingestion OR snippet-based text search
- Raw document access requires a new endpoint

The most impactful quick wins are:
1. Add `doc_id` to citations (**minimal code change**)
2. Create raw document download endpoint (**required for any highlighting**)
3. Return `text_plain` snippet in citations (**enables search-based fallback**)

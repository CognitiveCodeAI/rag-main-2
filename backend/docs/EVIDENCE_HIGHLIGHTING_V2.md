# Evidence Highlighting V2

Evidence Highlighting V2 provides fail-closed, claim-level highlighting for
native PDFs. A green **Verified Evidence** label means all of the following were
checked by the server:

1. The citation references a node that was included in the answer context.
2. The model supplied a verbatim supporting quote and a stable citation ID.
3. The quote occurs exactly once within that node's ordered source words.
4. The document ID, version, page, and content hash match.
5. Every returned rectangle is within the visible page bounds.

The browser renders normalized top-left rectangles supplied by the server. It
does not re-search or reinterpret the PDF text layer.

Before evidence hydration, the answer client also validates every structured
citation against the exact packed context. A citation is accepted only when its
node ID and page are an allowed pair and its normalized verbatim quote occurs
in that node. Invalid model output receives a bounded correction attempt; if it
still fails, answer generation fails closed instead of manufacturing a source.
A pure abstention must carry no citations.

## Evidence states

- `verified`: exact quote and original-PDF rectangles were independently
  resolved.
- `approximate`: text was found in a canonical/reconstructed source, but exact
  original-document coordinates are unavailable.
- `unavailable`: evidence could not be safely resolved. No guessed highlight is
  returned.

Only `verified` records are presented as verified in the PDF viewer.

## Compatibility and existing documents

Documents ingested before V2 do not contain ordered source words. Their existing
selectors remain usable for approximate canonical navigation, but cannot be
promoted to verified evidence.

`GET /v1/documents/{doc_id}/source-manifest` reports:

- `evidence_v2_coverage.nodes_with_source_spans`
- `evidence_v2_coverage.nodes_with_exact_source_spans`
- `evidence_v2_coverage.eligible_text_nodes`
- `evidence_v2_reingest_recommended`

For a stored native PDF, run:

```bash
cd backend
venv/bin/python -m scripts.backfill_evidence_v2 <graph_doc_id>
```

The command verifies the stored file hash, preserves graph/node identity and
embeddings, and replaces only node provenance and highlight artifacts. Scanned
PDFs still require an OCR provider that returns word or line coordinates;
text-only OCR remains approximate/unavailable by design.

Pass `--version N` to upgrade a specific document version. Without it, the
latest version is selected.

## Deployment

1. Apply Alembic revision `014`.
2. Deploy backend and frontend together because the API adds `rects` locators.
3. Validate a newly ingested native PDF before re-ingesting production
   documents.
4. Monitor verification reasons, especially:
   `exact_quote_not_in_cited_source_words`,
   `ambiguous_exact_quote_in_cited_node`, and
   `source_map_content_hash_mismatch`.
5. Keep `ENABLE_CROSS_FORMAT_HIGHLIGHTING=false` as the fail-safe rollback for
   source verification and highlighting.

## Acceptance criteria

- No wrong document, page, or evidence rectangle is labeled verified.
- Ambiguous quotes and stale source hashes fail closed.
- Rectangles remain aligned at all supported zoom levels and page rotations.
- ACL filtering removes a citation and its evidence record together.
- Existing documents are clearly labeled approximate or unavailable until
  re-ingested.

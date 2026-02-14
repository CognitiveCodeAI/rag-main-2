import { describe, expect, it } from "vitest";

import type { Citation } from "@/lib/api";
import {
  buildCanonicalHighlightRanges,
  getEvidenceFailureMessage,
  getVerifiedEvidenceHighlights,
} from "@/components/source-viewer/evidence";

function makeCitation(): Citation {
  return {
    page_no: 14,
    node_id: "node-1",
    doc_id: "doc-1",
    evidence_spans: [],
    evidence_verification: [],
  };
}

describe("source-viewer evidence mapping", () => {
  it("maps multiple FOUND evidence spans to verified highlights", () => {
    const citation = makeCitation();
    citation.evidence_spans = [
      {
        doc_id: "doc-1",
        page_index: 14,
        page_index_base: 1,
        quote_text: "Initial Franchise Fee is due at signing.",
        locator: { type: "text_offsets", start: 120, end: 158 },
        confidence: 1,
      },
      {
        doc_id: "doc-1",
        page_index: 23,
        page_index_base: 1,
        quote_text: "Development Fee is non-refundable.",
        locator: {
          type: "bbox",
          bbox: { x0: 12, y0: 44, x1: 180, y1: 78 },
          page_size: { width: 612, height: 792 },
        },
        confidence: 1,
      },
    ];
    citation.evidence_verification = [
      {
        status: "FOUND",
        matched_locator: { type: "text_offsets", start: 120, end: 158 },
        confidence: 1,
        reason: "exact_text_offsets_match",
      },
      {
        status: "FOUND",
        matched_locator: {
          type: "bbox",
          bbox: { x0: 12, y0: 44, x1: 180, y1: 78 },
          page_size: { width: 612, height: 792 },
        },
        confidence: 1,
        reason: "exact_bbox_match",
      },
    ];

    const highlights = getVerifiedEvidenceHighlights(citation);
    expect(highlights).toHaveLength(2);
    expect(highlights[0].pageNo).toBe(14);
    expect(highlights[0].locator.type).toBe("text_offsets");
    expect(highlights[1].pageNo).toBe(23);
    expect(highlights[1].locator.type).toBe("bbox");
  });

  it("returns no highlights and failure message when evidence is NOT_FOUND", () => {
    const citation = makeCitation();
    citation.evidence_spans = [
      {
        doc_id: "doc-1",
        page_index: 14,
        page_index_base: 1,
        quote_text: "Not present quote",
        locator: { type: "text_offsets", start: 10, end: 30 },
        confidence: 0,
      },
    ];
    citation.evidence_verification = [
      {
        status: "NOT_FOUND",
        matched_locator: null,
        confidence: 0,
        reason: "evidence_not_found_on_cited_page",
      },
    ];

    expect(getVerifiedEvidenceHighlights(citation)).toEqual([]);
    expect(getEvidenceFailureMessage(citation)).toBe("Evidence not found on cited page");
  });

  it("builds deterministic merged canonical highlight ranges from verified offsets", () => {
    const citation = makeCitation();
    citation.evidence_spans = [
      {
        doc_id: "doc-1",
        page_index: 1,
        page_index_base: 1,
        quote_text: "Alpha",
        locator: { type: "text_offsets", start: 5, end: 12 },
        confidence: 1,
      },
      {
        doc_id: "doc-1",
        page_index: 1,
        page_index_base: 1,
        quote_text: "Beta",
        locator: { type: "text_offsets", start: 12, end: 16 },
        confidence: 1,
      },
      {
        doc_id: "doc-1",
        page_index: 1,
        page_index_base: 1,
        quote_text: "Gamma",
        locator: { type: "text_offsets", start: 40, end: 45 },
        confidence: 1,
      },
    ];
    citation.evidence_verification = [
      {
        status: "FOUND",
        matched_locator: { type: "text_offsets", start: 5, end: 12 },
        confidence: 1,
        reason: "exact_text_offsets_match",
      },
      {
        status: "FOUND",
        matched_locator: { type: "text_offsets", start: 12, end: 16 },
        confidence: 1,
        reason: "exact_text_offsets_match",
      },
      {
        status: "FOUND",
        matched_locator: { type: "text_offsets", start: 40, end: 45 },
        confidence: 1,
        reason: "exact_text_offsets_match",
      },
    ];

    const ranges = buildCanonicalHighlightRanges(citation, 200);
    expect(ranges).toEqual([
      { start: 5, end: 16 },
      { start: 40, end: 45 },
    ]);
  });
});

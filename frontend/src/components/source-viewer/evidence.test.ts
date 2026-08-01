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
        grade: "verified",
        matched_locator: { type: "text_offsets", start: 120, end: 158 },
        confidence: 1,
        reason: "exact_text_offsets_match",
      },
      {
        status: "FOUND",
        grade: "verified",
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

  it("fails closed when a legacy verification has no explicit verified grade", () => {
    const citation = makeCitation();
    citation.evidence_spans = [
      {
        doc_id: "doc-1",
        page_index: 14,
        page_index_base: 1,
        quote_text: "Legacy quote",
        locator: { type: "text_offsets", start: 10, end: 22 },
        confidence: 1,
      },
    ];
    citation.evidence_verification = [
      {
        status: "FOUND",
        matched_locator: { type: "text_offsets", start: 10, end: 22 },
        confidence: 1,
        reason: "legacy_response_without_grade",
      },
    ];

    expect(getVerifiedEvidenceHighlights(citation)).toEqual([]);
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
        grade: "verified",
        matched_locator: { type: "text_offsets", start: 5, end: 12 },
        confidence: 1,
        reason: "exact_text_offsets_match",
      },
      {
        status: "FOUND",
        grade: "verified",
        matched_locator: { type: "text_offsets", start: 12, end: 16 },
        confidence: 1,
        reason: "exact_text_offsets_match",
      },
      {
        status: "FOUND",
        grade: "verified",
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

  it("uses only V2 verified rectangle records for original-PDF highlighting", () => {
    const citation = makeCitation();
    citation.evidence_records = [
      {
        schema_version: "2.0",
        citation_id: "C1",
        doc_id: "doc-1",
        document_version: 1,
        node_id: "node-1",
        page: 14,
        exact_quote: "Exact supporting words.",
        source_hash: "sha256:test",
        status: "verified",
        verification_reason: "exact_unique_quote_with_source_rectangles",
        locator: {
          type: "rects",
          coordinate_system: "normalized_top_left",
          rects: [{ x0: 0.1, y0: 0.2, x1: 0.5, y1: 0.23 }],
          page_rotation: 0,
        },
        confidence: 1,
      },
    ];

    const highlights = getVerifiedEvidenceHighlights(citation);
    expect(highlights).toHaveLength(1);
    expect(highlights[0].locator.type).toBe("rects");
    expect(getEvidenceFailureMessage(citation)).toBeNull();
  });

  it("does not present approximate V2 evidence as verified", () => {
    const citation = makeCitation();
    citation.evidence_records = [
      {
        schema_version: "2.0",
        citation_id: "C1",
        doc_id: "doc-1",
        document_version: 1,
        node_id: "node-1",
        page: 14,
        exact_quote: "Legacy reconstructed text.",
        source_hash: "sha256:test",
        status: "approximate",
        verification_reason: "exact_quote_match_on_page",
        locator: { type: "text_offsets", start: 10, end: 36 },
        confidence: 1,
      },
    ];

    expect(getVerifiedEvidenceHighlights(citation)).toEqual([]);
    expect(getEvidenceFailureMessage(citation)).toContain("approximate");
  });
});

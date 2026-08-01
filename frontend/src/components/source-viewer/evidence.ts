import type { Citation, EvidenceLocator } from "@/lib/api";

export interface VerifiedEvidenceHighlight {
  pageNo: number; // 1-based page index
  locator: EvidenceLocator;
  quoteText: string;
  confidence: number;
  sourceSection?: string | null;
}

export interface TextRange {
  start: number;
  end: number;
}

function isValidTextOffsets(locator: EvidenceLocator): locator is Extract<EvidenceLocator, { type: "text_offsets" }> {
  return (
    locator.type === "text_offsets"
    && Number.isInteger(locator.start)
    && Number.isInteger(locator.end)
    && locator.start >= 0
    && locator.end > locator.start
  );
}

function isValidBbox(locator: EvidenceLocator): locator is Extract<EvidenceLocator, { type: "bbox" }> {
  return locator.type === "bbox";
}

export function getVerifiedEvidenceHighlights(citation?: Citation): VerifiedEvidenceHighlight[] {
  if (citation?.evidence_records?.length) {
    return citation.evidence_records
      .filter(
        (record) =>
          record.status === "verified"
          && record.locator?.type === "rects"
          && record.locator.rects.length > 0,
      )
      .map((record) => ({
        pageNo: record.page,
        locator: record.locator!,
        quoteText: record.exact_quote.trim(),
        confidence: record.confidence,
      }));
  }

  if (!citation?.evidence_spans?.length) {
    return [];
  }
  const verifications = citation.evidence_verification || [];
  const verified: VerifiedEvidenceHighlight[] = [];

  for (let i = 0; i < citation.evidence_spans.length; i += 1) {
    const span = citation.evidence_spans[i];
    const verification = verifications[i];
    if (
      !verification
      || verification.status !== "FOUND"
      || verification.grade !== "verified"
      || !verification.matched_locator
    ) {
      continue;
    }
    const locator = verification.matched_locator;
    if (!isValidTextOffsets(locator) && !isValidBbox(locator)) {
      continue;
    }

    const pageNo = span.page_index;
    if (!Number.isInteger(pageNo) || pageNo < 1) {
      continue;
    }

    verified.push({
      pageNo,
      locator,
      quoteText: (span.quote_text || "").trim(),
      confidence: Number.isFinite(verification.confidence)
        ? verification.confidence
        : (Number.isFinite(span.confidence) ? span.confidence : 0),
      sourceSection: span.source_section,
    });
  }

  return verified;
}

export function buildCanonicalHighlightRanges(
  citation: Citation | undefined,
  canonicalTextLength: number,
): TextRange[] {
  if (!citation || canonicalTextLength <= 0) {
    return [];
  }
  const recordLocators = citation.evidence_records
    ?.filter((record) => record.status !== "unavailable" && record.locator?.type === "text_offsets")
    .map((record) => record.locator as Extract<EvidenceLocator, { type: "text_offsets" }>);
  const legacyLocators = getVerifiedEvidenceHighlights(citation)
    .filter(
      (
        h,
      ): h is VerifiedEvidenceHighlight & { locator: Extract<EvidenceLocator, { type: "text_offsets" }> } =>
        h.locator.type === "text_offsets",
    )
    .map((h) => h.locator);
  const locators = recordLocators?.length ? recordLocators : legacyLocators;
  const ranges = locators
    .map((locator) => {
      const start = Math.max(0, Math.min(locator.start, canonicalTextLength));
      const end = Math.max(start, Math.min(locator.end, canonicalTextLength));
      return { start, end };
    })
    .filter((r) => r.end > r.start)
    .sort((a, b) => a.start - b.start);

  if (!ranges.length) {
    return [];
  }

  const merged: TextRange[] = [];
  for (const range of ranges) {
    const last = merged[merged.length - 1];
    if (!last || range.start > last.end) {
      merged.push({ ...range });
      continue;
    }
    last.end = Math.max(last.end, range.end);
  }
  return merged;
}

export function getEvidenceFailureMessage(citation?: Citation): string | null {
  if (!citation) {
    return null;
  }
  const highlights = getVerifiedEvidenceHighlights(citation);
  if (highlights.length > 0) {
    return null;
  }
  if (citation.evidence_records?.some((record) => record.status === "approximate")) {
    return "Exact source coordinates unavailable; this citation is approximate";
  }
  return "Evidence not found on cited page";
}

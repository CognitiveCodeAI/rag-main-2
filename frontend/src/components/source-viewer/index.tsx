"use client";

import * as React from "react";

import { Citation } from "@/lib/api";
import { PDFViewer, CitationHighlight } from "@/components/pdf-viewer";
import { HTMLSourceViewer } from "@/components/source-viewer/html-viewer";
import { getEvidenceFailureMessage, getVerifiedEvidenceHighlights } from "@/components/source-viewer/evidence";

interface SourceViewerProps {
  open: boolean;
  onClose: () => void;
  title?: string;
  url: string;
  docId: string;
  citation?: Citation;
}

function isPdfCitation(citation?: Citation): boolean {
  if (!citation) return false;
  if (citation.source_type?.toLowerCase() === "pdf") return true;
  if (citation.mime_type?.toLowerCase().includes("pdf")) return true;
  if (citation.raw_url?.toLowerCase().endsWith(".pdf")) return true;
  if (citation.bbox || citation.page_size) return true;
  return false;
}

export function SourceViewer({
  open,
  onClose,
  title,
  url,
  docId,
  citation,
}: SourceViewerProps) {
  const pdfMode = isPdfCitation(citation);

  const verifiedHighlights: CitationHighlight[] = React.useMemo(() => {
    if (!citation) return [];
    return getVerifiedEvidenceHighlights(citation).map((entry) => ({
      page_no: entry.pageNo,
      locator: entry.locator,
      quote_text: entry.quoteText,
      confidence: entry.confidence,
      source_section: entry.sourceSection ?? undefined,
    }));
  }, [citation]);
  const evidenceFailureMessage = React.useMemo(
    () => getEvidenceFailureMessage(citation),
    [citation],
  );

  if (pdfMode) {
    return (
      <PDFViewer
        url={url}
        open={open}
        onClose={onClose}
        highlights={verifiedHighlights}
        evidenceFailureMessage={evidenceFailureMessage}
        title={title}
      />
    );
  }

  return (
    <HTMLSourceViewer
      open={open}
      onClose={onClose}
      title={title}
      docId={docId}
      citation={citation}
    />
  );
}

export default SourceViewer;

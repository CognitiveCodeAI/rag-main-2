"use client";

import * as React from "react";

import { Citation } from "@/lib/api";
import { PDFViewer, CitationHighlight } from "@/components/pdf-viewer";
import { HTMLSourceViewer } from "@/components/source-viewer/html-viewer";

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

  const highlight: CitationHighlight | undefined = citation
    ? {
        page_no: citation.page_no || 1,
        bbox: citation.bbox,
        page_size: citation.page_size,
        anchor_snippet: citation.anchor_snippet || citation.text,
        label: citation.label,
      }
    : undefined;

  if (pdfMode) {
    return (
      <PDFViewer
        url={url}
        open={open}
        onClose={onClose}
        highlight={highlight}
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

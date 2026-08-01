"use client";

import * as React from "react";
import { AlertCircle, CheckCircle2, FileText } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { SourceMapResponse, Citation } from "@/lib/api";
import { buildCanonicalHighlightRanges, getEvidenceFailureMessage } from "@/components/source-viewer/evidence";

interface HTMLSourceViewerProps {
  open: boolean;
  onClose: () => void;
  title?: string;
  docId: string;
  citation?: Citation;
}

export function HTMLSourceViewer({
  open,
  onClose,
  title,
  docId,
  citation,
}: HTMLSourceViewerProps) {
  const [sourceMap, setSourceMap] = React.useState<SourceMapResponse | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (!open) return;

    const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    const sourceMapPath = citation?.source_map_url || `/v1/documents/${docId}/source-map`;
    const sourceMapUrl = sourceMapPath.startsWith("http")
      ? sourceMapPath
      : `${apiUrl}${sourceMapPath}`;

    let cancelled = false;
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await fetch(sourceMapUrl);
        if (!res.ok) {
          throw new Error(`Failed to load source map (${res.status})`);
        }
        const data = (await res.json()) as SourceMapResponse;
        if (!cancelled) {
          setSourceMap(data);
        }
      } catch (err) {
        if (!cancelled) {
          const message = err instanceof Error ? err.message : "Failed to load source map";
          setError(message);
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    load();
    return () => {
      cancelled = true;
    };
  }, [open, citation?.source_map_url, docId]);

  const renderHighlightedText = React.useMemo(() => {
    const canonicalText = sourceMap?.canonical_text || "";
    const ranges = buildCanonicalHighlightRanges(citation, canonicalText.length);

    if (!canonicalText) {
      return null;
    }

    if (!ranges.length) {
      return <span>{canonicalText}</span>;
    }

    const fragments: React.ReactNode[] = [];
    let cursor = 0;
    ranges.forEach((range, index) => {
      if (cursor < range.start) {
        fragments.push(
          <span key={`text-${index}`}>{canonicalText.slice(cursor, range.start)}</span>,
        );
      }
      fragments.push(
        <mark key={`mark-${index}`} data-highlight="active">
          {canonicalText.slice(range.start, range.end)}
        </mark>,
      );
      cursor = range.end;
    });
    if (cursor < canonicalText.length) {
      fragments.push(<span key="text-tail">{canonicalText.slice(cursor)}</span>);
    }

    return <>{fragments}</>;
  }, [sourceMap?.canonical_text, citation]);

  const resolveStatus = citation?.evidence_status || citation?.resolve_status || "unavailable";
  const evidenceFailureMessage = getEvidenceFailureMessage(citation);
  const showEvidenceNotFound = Boolean(evidenceFailureMessage);

  return (
    <Sheet open={open} onOpenChange={(next) => !next && onClose()}>
      <SheetContent className="w-full sm:max-w-4xl">
        <SheetHeader>
          <SheetTitle className="flex items-center gap-2">
            <FileText className="h-4 w-4" />
            {title || "Document Source"}
          </SheetTitle>
          <SheetDescription className="sr-only">
            Canonical document source with citation evidence and verification status.
          </SheetDescription>
        </SheetHeader>

        <div className="mt-4 flex items-center gap-2">
          {resolveStatus === "verified" ? (
            <Badge variant="default" className="gap-1">
              <CheckCircle2 className="h-3 w-3" />
              Verified Evidence
            </Badge>
          ) : resolveStatus === "approximate" || resolveStatus === "exact" || resolveStatus === "fuzzy" ? (
            <Badge variant="secondary">Approximate Source</Badge>
          ) : (
            <Badge variant="destructive" className="gap-1">
              <AlertCircle className="h-3 w-3" />
              Unresolved
            </Badge>
          )}
          {citation?.snapshot_id && (
            <Badge variant="outline">Snapshot {citation.snapshot_id.slice(0, 8)}</Badge>
          )}
        </div>

        {showEvidenceNotFound && (
          <div className="mt-3 rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
            {evidenceFailureMessage}
            {citation?.resolve_reason ? ` (${citation.resolve_reason})` : ""}
          </div>
        )}

        <ScrollArea className="mt-4 h-[calc(100vh-13rem)] rounded-md border p-4">
          {loading && <p className="text-sm text-muted-foreground">Loading canonical source...</p>}
          {error && <p className="text-sm text-destructive">{error}</p>}
          {!loading && !error && sourceMap && (
            <pre className="whitespace-pre-wrap text-sm leading-6">{renderHighlightedText}</pre>
          )}
        </ScrollArea>
      </SheetContent>
    </Sheet>
  );
}

export default HTMLSourceViewer;

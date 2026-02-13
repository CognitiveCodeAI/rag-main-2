"use client";

import * as React from "react";
import { AlertCircle, CheckCircle2, FileText } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { SourceMapResponse, Citation } from "@/lib/api";

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
    const position = citation?.selector_bundle?.text_position;
    const status = citation?.resolve_status || "unresolved";

    if (!canonicalText) {
      return null;
    }

    if (!position || status === "unresolved") {
      return <span>{canonicalText}</span>;
    }

    const start = Math.max(0, Math.min(position.start, canonicalText.length));
    const end = Math.max(start, Math.min(position.end, canonicalText.length));

    return (
      <>
        {canonicalText.slice(0, start)}
        <mark data-highlight="active">{canonicalText.slice(start, end)}</mark>
        {canonicalText.slice(end)}
      </>
    );
  }, [sourceMap?.canonical_text, citation?.selector_bundle?.text_position, citation?.resolve_status]);

  const resolveStatus = citation?.resolve_status || "unresolved";

  return (
    <Sheet open={open} onOpenChange={(next) => !next && onClose()}>
      <SheetContent className="w-full sm:max-w-4xl">
        <SheetHeader>
          <SheetTitle className="flex items-center gap-2">
            <FileText className="h-4 w-4" />
            {title || "Document Source"}
          </SheetTitle>
        </SheetHeader>

        <div className="mt-4 flex items-center gap-2">
          {resolveStatus === "exact" ? (
            <Badge variant="default" className="gap-1">
              <CheckCircle2 className="h-3 w-3" />
              Verified
            </Badge>
          ) : resolveStatus === "fuzzy" ? (
            <Badge variant="secondary">Fuzzy Match</Badge>
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

        {resolveStatus === "unresolved" && (
          <div className="mt-3 rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
            Cannot verify exact passage for this citation.
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


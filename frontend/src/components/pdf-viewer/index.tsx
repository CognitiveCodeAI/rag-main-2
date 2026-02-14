"use client";

/**
 * PDF Viewer with Citation Highlighting
 * 
 * Enables "click citation → open doc → jump to location → highlight" functionality.
 * Uses pdfjs-dist for PDF rendering with custom highlight overlays.
 * 
 * Highlight rendering:
 * 1. Verified bbox overlays
 * 2. Verified exact quote overlays
 */

import React, { useEffect, useRef, useState, useCallback } from "react";
import * as pdfjsLib from "pdfjs-dist";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import {
  ChevronLeft, 
  ChevronRight, 
  ZoomIn, 
  ZoomOut, 
  X, 
  FileText, 
  Target,
  Download,
  RotateCw,
  Maximize2,
  Minimize2,
  ChevronFirst,
  ChevronLast,
  Loader2,
  AlertCircle,
} from "lucide-react";

// Configure PDF.js worker - use unpkg which has latest npm versions
if (typeof window !== "undefined") {
  pdfjsLib.GlobalWorkerOptions.workerSrc = `//unpkg.com/pdfjs-dist@${pdfjsLib.version}/build/pdf.worker.min.mjs`;
}

export interface CitationHighlight {
  page_no: number;
  locator:
    | {
        type: "bbox";
        bbox: {
          x0: number;
          y0: number;
          x1: number;
          y1: number;
        };
        page_size?: {
          width: number;
          height: number;
        };
      }
    | {
        type: "text_offsets";
        start: number;
        end: number;
      };
  quote_text: string;
  confidence?: number;
  source_section?: string;
}

interface PDFViewerProps {
  /** URL to load PDF from */
  url: string;
  /** Whether the viewer is open */
  open: boolean;
  /** Callback when viewer is closed */
  onClose: () => void;
  /** Verified evidence highlights */
  highlights?: CitationHighlight[];
  /** Resolver failure reason */
  evidenceFailureMessage?: string | null;
  /** Document title for header */
  title?: string;
}

// Interface for text highlight rectangles
interface TextHighlightRect {
  x: number;
  y: number;
  width: number;
  height: number;
}

function normalizeForSearch(value: string): string {
  return value
    .normalize("NFKC")
    .replace(/\s+/g, " ")
    .trim()
    .toLowerCase();
}

function mergeHighlightsByLine(rects: TextHighlightRect[]): TextHighlightRect[] {
  if (rects.length <= 1) return rects;

  const sorted = [...rects].sort((a, b) => {
    if (Math.abs(a.y - b.y) <= 4) return a.x - b.x;
    return a.y - b.y;
  });

  const merged: TextHighlightRect[] = [];
  for (const rect of sorted) {
    const last = merged[merged.length - 1];
    if (!last) {
      merged.push({ ...rect });
      continue;
    }

    const lineThreshold = Math.max(4, Math.min(last.height, rect.height) * 0.6);
    const sameLine = Math.abs(rect.y - last.y) <= lineThreshold;
    const gap = rect.x - (last.x + last.width);
    const gapThreshold = Math.max(10, rect.height * 1.2);

    if (sameLine && gap <= gapThreshold) {
      const left = Math.min(last.x, rect.x);
      const top = Math.min(last.y, rect.y);
      const right = Math.max(last.x + last.width, rect.x + rect.width);
      const bottom = Math.max(last.y + last.height, rect.y + rect.height);
      last.x = left;
      last.y = top;
      last.width = right - left;
      last.height = bottom - top;
      continue;
    }

    merged.push({ ...rect });
  }

  return merged;
}

export function PDFViewer({
  url,
  open,
  onClose,
  highlights = [],
  evidenceFailureMessage,
  title,
}: PDFViewerProps) {
  const [pdf, setPdf] = useState<pdfjsLib.PDFDocumentProxy | null>(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [numPages, setNumPages] = useState(0);
  const [scale, setScale] = useState(1.0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pageInput, setPageInput] = useState("1");
  const [isFullWidth, setIsFullWidth] = useState(false);
  const [textHighlights, setTextHighlights] = useState<TextHighlightRect[]>([]);
  const [bboxHighlights, setBboxHighlights] = useState<TextHighlightRect[]>([]);
  const [renderFailureMessage, setRenderFailureMessage] = useState<string | null>(null);
  
  const containerRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const scrollAreaRef = useRef<HTMLDivElement>(null);

  const firstHighlightedPage = highlights[0]?.page_no || 1;
  const highlightsForCurrentPage = React.useMemo(
    () => highlights.filter((item) => item.page_no === currentPage),
    [highlights, currentPage],
  );

  const toViewportRect = useCallback(
    (
      viewport: pdfjsLib.PageViewport,
      bbox: { x0: number; y0: number; x1: number; y1: number },
    ): TextHighlightRect => {
      const [vx0, vy0, vx1, vy1] = viewport.convertToViewportRectangle([
        bbox.x0,
        bbox.y0,
        bbox.x1,
        bbox.y1,
      ]);
      return {
        x: Math.max(0, Math.min(vx0, vx1)),
        y: Math.max(0, Math.min(vy0, vy1)),
        width: Math.abs(vx1 - vx0),
        height: Math.abs(vy1 - vy0),
      };
    },
    [],
  );

  const findExactQuoteHighlights = useCallback(async (
    page: pdfjsLib.PDFPageProxy,
    viewport: pdfjsLib.PageViewport,
    quoteText: string,
  ): Promise<TextHighlightRect[]> => {
    try {
      const normalizedQuote = normalizeForSearch(quoteText);
      if (!normalizedQuote || normalizedQuote.length < 3) return [];

      const textContent = await page.getTextContent();
      const items = textContent.items as Array<{
        str: string;
        transform: number[];
        width: number;
        height: number;
      }>;

      const sortedItems = items
        .map((item) => {
          const [x, y] = viewport.convertToViewportPoint(item.transform[4], item.transform[5]);
          return { item, x, y };
        })
        .sort((a, b) => {
          const yDelta = a.y - b.y;
          if (Math.abs(yDelta) > 4) return yDelta;
          return a.x - b.x;
        });

      const entries: Array<{
        item: {
          str: string;
          transform: number[];
          width: number;
          height: number;
        };
        start: number;
        end: number;
      }> = [];
      let pageText = "";

      for (const entry of sortedItems) {
        const normalizedItem = normalizeForSearch(entry.item.str || "");
        if (!normalizedItem) continue;
        if (pageText.length > 0) pageText += " ";
        const start = pageText.length;
        pageText += normalizedItem;
        const end = pageText.length;
        entries.push({ item: entry.item, start, end });
      }

      if (!pageText) return [];

      const matchedGroups: TextHighlightRect[][] = [];
      let fromIndex = 0;
      while (fromIndex < pageText.length) {
        const matchStart = pageText.indexOf(normalizedQuote, fromIndex);
        if (matchStart < 0) break;
        const matchEnd = matchStart + normalizedQuote.length;
        fromIndex = matchEnd;

        const rawRects: TextHighlightRect[] = [];
        for (const entry of entries) {
          const overlaps = entry.start < matchEnd && entry.end > matchStart;
          if (!overlaps) continue;

          const item = entry.item;
          const [x, y] = viewport.convertToViewportPoint(item.transform[4], item.transform[5]);
          const [x2] = viewport.convertToViewportPoint(
            item.transform[4] + (item.width || 0),
            item.transform[5],
          );
          const width = Math.max(6, Math.abs(x2 - x));
          const glyphHeight = Math.max(
            10,
            Math.abs(item.transform[3] || 0) * viewport.scale || 12 * viewport.scale,
          );
          rawRects.push({
            x: Math.max(0, x),
            y: Math.max(0, y - glyphHeight),
            width,
            height: Math.max(10, glyphHeight * 1.15),
          });
        }

        matchedGroups.push(mergeHighlightsByLine(rawRects));
        if (matchedGroups.length > 1) {
          // Ambiguous quote on same page; fail closed.
          return [];
        }
      }

      return matchedGroups[0] || [];
    } catch (err) {
      console.error("Error finding exact quote highlights:", err);
      return [];
    }
  }, []);
  
  // Load PDF when URL changes
  useEffect(() => {
    if (!open || !url) return;
    let cancelled = false;
    
    const loadPDF = async () => {
      setLoading(true);
      setError(null);
      try {
        const loadingTask = pdfjsLib.getDocument(url);
        const pdfDoc = await loadingTask.promise;
        if (cancelled) return;
        setPdf(pdfDoc);
        setNumPages(pdfDoc.numPages);
        
        // Jump to first verified highlight page if specified.
        const targetPage = firstHighlightedPage;
        setCurrentPage(targetPage);
        setPageInput(String(targetPage));
        
        setLoading(false);
      } catch (err) {
        if (cancelled) return;
        console.error("Failed to load PDF:", err);
        setError(`Failed to load PDF: ${err}`);
        setLoading(false);
      }
    };
    
    loadPDF();
    return () => {
      cancelled = true;
    };
  }, [url, open, firstHighlightedPage]);

  // Render current page
  useEffect(() => {
    if (!pdf || !canvasRef.current) return;

    const renderPage = async () => {
      try {
        const page = await pdf.getPage(currentPage);
        const viewport = page.getViewport({ scale });

        const canvas = canvasRef.current!;
        const context = canvas.getContext("2d")!;

        canvas.height = viewport.height;
        canvas.width = viewport.width;

        await page.render({
          canvas,
          canvasContext: context,
          viewport,
        }).promise;

        // Clear previous highlights
        const nextTextHighlights: TextHighlightRect[] = [];
        const nextBboxHighlights: TextHighlightRect[] = [];

        for (const item of highlightsForCurrentPage) {
          if (item.locator.type === "bbox") {
            nextBboxHighlights.push(toViewportRect(viewport, item.locator.bbox));
          } else if (item.quote_text) {
            const exactRects = await findExactQuoteHighlights(page, viewport, item.quote_text);
            nextTextHighlights.push(...exactRects);
          }
        }

        const mergedTextHighlights = mergeHighlightsByLine(nextTextHighlights);
        setBboxHighlights(nextBboxHighlights);
        setTextHighlights(mergedTextHighlights);
        const hasRenderable = nextBboxHighlights.length > 0 || mergedTextHighlights.length > 0;
        setRenderFailureMessage(
          highlightsForCurrentPage.length > 0 && !hasRenderable
            ? "Evidence not found on cited page"
            : null,
        );
      } catch (err) {
        console.error("Failed to render page:", err);
        setRenderFailureMessage("Evidence not found on cited page");
      }
    };

    renderPage();
  }, [pdf, currentPage, scale, highlightsForCurrentPage, findExactQuoteHighlights, toViewportRect]);
  
  // Navigation handlers
  const goToFirstPage = () => { setCurrentPage(1); setPageInput("1"); };
  const goToLastPage = () => { setCurrentPage(numPages); setPageInput(String(numPages)); };
  const goToPrevPage = () => { 
    const newPage = Math.max(1, currentPage - 1);
    setCurrentPage(newPage); 
    setPageInput(String(newPage)); 
  };
  const goToNextPage = () => { 
    const newPage = Math.min(numPages, currentPage + 1);
    setCurrentPage(newPage); 
    setPageInput(String(newPage)); 
  };
  
  // Page input handler
  const handlePageInput = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      const page = parseInt(pageInput, 10);
      if (!isNaN(page) && page >= 1 && page <= numPages) {
        setCurrentPage(page);
      } else {
        setPageInput(String(currentPage));
      }
    }
  };
  
  // Zoom handlers
  const zoomIn = () => setScale((s) => Math.min(3, s + 0.25));
  const zoomOut = () => setScale((s) => Math.max(0.5, s - 0.25));
  const resetZoom = () => setScale(1.0);
  
  const hasHighlights = highlights.length > 0;
  const hasBboxLocator = highlights.some((item) => item.locator.type === "bbox");
  const visibleFailureMessage = !hasHighlights
    ? (evidenceFailureMessage || null)
    : renderFailureMessage;

  // Jump to first verified citation span
  const jumpToCitation = () => {
    if (firstHighlightedPage >= 1) {
      setCurrentPage(firstHighlightedPage);
      setPageInput(String(firstHighlightedPage));
    }
  };
  
  // Download PDF
  const downloadPDF = () => {
    window.open(url, "_blank");
  };
  
  // Keyboard shortcuts
  useEffect(() => {
    if (!open) return;
    
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "ArrowLeft" || e.key === "PageUp") {
        e.preventDefault();
        goToPrevPage();
      } else if (e.key === "ArrowRight" || e.key === "PageDown") {
        e.preventDefault();
        goToNextPage();
      } else if (e.key === "Home") {
        e.preventDefault();
        goToFirstPage();
      } else if (e.key === "End") {
        e.preventDefault();
        goToLastPage();
      } else if (e.key === "+" || e.key === "=") {
        e.preventDefault();
        zoomIn();
      } else if (e.key === "-") {
        e.preventDefault();
        zoomOut();
      } else if (e.key === "Escape") {
        onClose();
      }
    };
    
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [open, currentPage, numPages]);
  
  // Get highlight type badge based on available data
  const getHighlightBadge = () => {
    if (!hasHighlights) return null;

    if (hasBboxLocator) {
      return (
        <Badge variant="secondary" className="bg-yellow-500/10 text-yellow-600 dark:text-yellow-400 border-yellow-500/30">
          <Target className="h-3 w-3 mr-1" />
          Verified (BBox)
        </Badge>
      );
    }

    if (highlights.some((item) => item.locator.type === "text_offsets")) {
      return (
        <Badge variant="secondary" className="bg-orange-500/10 text-orange-600 dark:text-orange-400 border-orange-500/30">
          <Target className="h-3 w-3 mr-1" />
          Verified (Text)
        </Badge>
      );
    }

    return (
      <Badge variant="secondary" className="bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-500/30">
        <FileText className="h-3 w-3 mr-1" />
        Source Page
      </Badge>
    );
  };

  return (
    <Sheet open={open} onOpenChange={(o) => !o && onClose()}>
      <SheetContent 
        side="right" 
        showCloseButton={false}
        className={cn(
          "flex flex-col p-0 gap-0 transition-all duration-300",
          isFullWidth 
            ? "w-full !max-w-full sm:!max-w-full" 
            : "w-full sm:!max-w-[70vw] lg:!max-w-[60vw] xl:!max-w-[55vw]"
        )}
      >
        {/* Header */}
        <SheetHeader className="px-4 py-3 border-b bg-muted/30 flex-shrink-0">
          <div className="flex items-center justify-between gap-4">
            <SheetTitle className="flex items-center gap-2 text-base font-semibold truncate">
              <FileText className="h-5 w-5 flex-shrink-0 text-primary" />
              <span className="truncate">{title || "Document"}</span>
            </SheetTitle>
            
            <div className="flex items-center gap-1">
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => setIsFullWidth(!isFullWidth)}>
                    {isFullWidth ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
                  </Button>
                </TooltipTrigger>
                <TooltipContent>{isFullWidth ? "Collapse" : "Expand"}</TooltipContent>
              </Tooltip>
              
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button variant="ghost" size="icon" className="h-8 w-8" onClick={downloadPDF}>
                    <Download className="h-4 w-4" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent>Download PDF</TooltipContent>
              </Tooltip>
              
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button variant="ghost" size="icon" className="h-8 w-8" onClick={onClose}>
                    <X className="h-4 w-4" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent>Close (Esc)</TooltipContent>
              </Tooltip>
            </div>
          </div>
        </SheetHeader>
        
        {/* Toolbar */}
        <div className="px-4 py-2 border-b bg-background flex items-center justify-between gap-2 flex-wrap">
          {/* Navigation */}
          <div className="flex items-center gap-1">
            <Tooltip>
              <TooltipTrigger asChild>
                <Button variant="outline" size="icon" className="h-8 w-8" onClick={goToFirstPage} disabled={currentPage <= 1}>
                  <ChevronFirst className="h-4 w-4" />
                </Button>
              </TooltipTrigger>
              <TooltipContent>First Page (Home)</TooltipContent>
            </Tooltip>
            
            <Tooltip>
              <TooltipTrigger asChild>
                <Button variant="outline" size="icon" className="h-8 w-8" onClick={goToPrevPage} disabled={currentPage <= 1}>
                  <ChevronLeft className="h-4 w-4" />
                </Button>
              </TooltipTrigger>
              <TooltipContent>Previous Page (←)</TooltipContent>
            </Tooltip>
            
            <div className="flex items-center gap-1.5 px-2">
              <Input
                type="text"
                value={pageInput}
                onChange={(e) => setPageInput(e.target.value)}
                onKeyDown={handlePageInput}
                onBlur={() => setPageInput(String(currentPage))}
                className="h-8 w-14 text-center text-sm"
              />
              <span className="text-sm text-muted-foreground whitespace-nowrap">
                of {numPages}
              </span>
            </div>
            
            <Tooltip>
              <TooltipTrigger asChild>
                <Button variant="outline" size="icon" className="h-8 w-8" onClick={goToNextPage} disabled={currentPage >= numPages}>
                  <ChevronRight className="h-4 w-4" />
                </Button>
              </TooltipTrigger>
              <TooltipContent>Next Page (→)</TooltipContent>
            </Tooltip>
            
            <Tooltip>
              <TooltipTrigger asChild>
                <Button variant="outline" size="icon" className="h-8 w-8" onClick={goToLastPage} disabled={currentPage >= numPages}>
                  <ChevronLast className="h-4 w-4" />
                </Button>
              </TooltipTrigger>
              <TooltipContent>Last Page (End)</TooltipContent>
            </Tooltip>
          </div>
          
          <Separator orientation="vertical" className="h-6 hidden sm:block" />
          
          {/* Zoom controls */}
          <div className="flex items-center gap-1">
            <Tooltip>
              <TooltipTrigger asChild>
                <Button variant="outline" size="icon" className="h-8 w-8" onClick={zoomOut} disabled={scale <= 0.5}>
                  <ZoomOut className="h-4 w-4" />
                </Button>
              </TooltipTrigger>
              <TooltipContent>Zoom Out (-)</TooltipContent>
            </Tooltip>
            
            <Button 
              variant="ghost" 
              className="h-8 px-2 text-sm font-medium min-w-[60px]"
              onClick={resetZoom}
            >
              {Math.round(scale * 100)}%
            </Button>
            
            <Tooltip>
              <TooltipTrigger asChild>
                <Button variant="outline" size="icon" className="h-8 w-8" onClick={zoomIn} disabled={scale >= 3}>
                  <ZoomIn className="h-4 w-4" />
                </Button>
              </TooltipTrigger>
              <TooltipContent>Zoom In (+)</TooltipContent>
            </Tooltip>
          </div>
          
          {/* Citation highlight controls */}
          {hasHighlights && (
            <>
              <Separator orientation="vertical" className="h-6 hidden sm:block" />
              <div className="flex items-center gap-2">
                {getHighlightBadge()}
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button 
                      variant="secondary" 
                      size="sm" 
                      className="h-8 gap-1.5"
                      onClick={jumpToCitation}
                    >
                      <Target className="h-3.5 w-3.5" />
                      <span className="hidden sm:inline">Page {firstHighlightedPage}</span>
                      <span className="sm:hidden">{firstHighlightedPage}</span>
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent>Jump to Citation</TooltipContent>
                </Tooltip>
              </div>
            </>
          )}
        </div>
        
        {/* PDF Content Area */}
        <ScrollArea className="flex-1 bg-muted/20" ref={scrollAreaRef}>
          <div 
            ref={containerRef}
            className="flex justify-center py-6 px-4 min-h-full"
          >
            {loading && (
              <div className="flex flex-col items-center justify-center h-[60vh] gap-4">
                <Loader2 className="h-10 w-10 animate-spin text-primary" />
                <p className="text-sm text-muted-foreground">Loading document...</p>
              </div>
            )}
            
            {error && (
              <div className="flex flex-col items-center justify-center h-[60vh] gap-4 text-center px-4">
                <div className="rounded-full bg-destructive/10 p-4">
                  <AlertCircle className="h-10 w-10 text-destructive" />
                </div>
                <div className="space-y-2">
                  <p className="font-medium text-destructive">Failed to load document</p>
                  <p className="text-sm text-muted-foreground max-w-md">{error}</p>
                </div>
                <Button variant="outline" onClick={() => window.location.reload()}>
                  <RotateCw className="h-4 w-4 mr-2" />
                  Retry
                </Button>
              </div>
            )}
            
            {!loading && !error && (
              <div className="relative inline-block">
                {visibleFailureMessage && (
                  <div className="mb-3 rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
                    {visibleFailureMessage}
                  </div>
                )}
                <canvas
                  ref={canvasRef}
                  className="shadow-xl rounded-sm bg-white"
                  style={{ maxWidth: "100%" }}
                />
                {/* Bbox highlight overlays */}
                {bboxHighlights.map((rect, i) => (
                  <div
                    key={`bbox-${i}`}
                    className="absolute pointer-events-none bg-yellow-400/35 border-2 border-yellow-500 rounded-sm shadow-md z-20"
                    style={{
                      left: `${rect.x}px`,
                      top: `${rect.y}px`,
                      width: `${rect.width}px`,
                      height: `${rect.height}px`,
                    }}
                  />
                ))}
                {/* Text highlight overlays */}
                {textHighlights.map((rect, i) => (
                  <div
                    key={`txt-${i}`}
                    className="absolute pointer-events-none bg-yellow-300/45 border border-yellow-500/90 rounded-sm shadow-md z-10"
                    style={{
                      left: `${rect.x}px`,
                      top: `${rect.y}px`,
                      width: `${rect.width}px`,
                      height: `${rect.height}px`,
                    }}
                  />
                ))}
              </div>
            )}
          </div>
        </ScrollArea>
        
        {/* Footer status bar */}
        {!loading && !error && (
          <div className="px-4 py-2 border-t bg-muted/30 text-xs text-muted-foreground flex items-center justify-between">
            <span>
              Page {currentPage} of {numPages}
              {hasHighlights && highlightsForCurrentPage.length > 0 && " • Viewing verified evidence"}
            </span>
            <span className="hidden sm:inline">
              Use arrow keys to navigate • +/- to zoom
            </span>
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}

export default PDFViewer;

"use client";

/**
 * PDF Viewer with Citation Highlighting
 * 
 * Enables "click citation → open doc → jump to location → highlight" functionality.
 * Uses pdfjs-dist for PDF rendering with custom highlight overlays.
 * 
 * Highlighting priority:
 * 1. bbox highlight - Direct coordinate-based highlighting (most precise)
 * 2. Text search fallback - Find anchor_snippet on page and highlight
 * 3. Page-only jump - Scroll to page when no other anchoring available
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
  MapPin
} from "lucide-react";

// Configure PDF.js worker - use unpkg which has latest npm versions
if (typeof window !== "undefined") {
  pdfjsLib.GlobalWorkerOptions.workerSrc = `//unpkg.com/pdfjs-dist@${pdfjsLib.version}/build/pdf.worker.min.mjs`;
}

export interface CitationHighlight {
  page_no: number;
  bbox?: {
    x0: number;
    y0: number;
    x1: number;
    y1: number;
  };
  page_size?: {
    width: number;
    height: number;
  };
  anchor_snippet?: string;
  label?: string;
}

interface PDFViewerProps {
  /** URL to load PDF from */
  url: string;
  /** Whether the viewer is open */
  open: boolean;
  /** Callback when viewer is closed */
  onClose: () => void;
  /** Citation to highlight */
  highlight?: CitationHighlight;
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

export function PDFViewer({ url, open, onClose, highlight, title }: PDFViewerProps) {
  const [pdf, setPdf] = useState<pdfjsLib.PDFDocumentProxy | null>(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [numPages, setNumPages] = useState(0);
  const [scale, setScale] = useState(1.0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pageInput, setPageInput] = useState("1");
  const [isFullWidth, setIsFullWidth] = useState(false);
  const [textHighlights, setTextHighlights] = useState<TextHighlightRect[]>([]);
  
  const containerRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const highlightRef = useRef<HTMLDivElement>(null);
  const scrollAreaRef = useRef<HTMLDivElement>(null);

  type PDFTextContentItem = {
    str?: string;
  };
  
  // Find and highlight text matching the anchor_snippet
  // Defined early to avoid initialization order issues
  const findTextHighlights = useCallback(async (
    page: pdfjsLib.PDFPageProxy,
    viewport: pdfjsLib.PageViewport,
    anchorSnippet: string
  ): Promise<TextHighlightRect[]> => {
    try {
      const textContent = await page.getTextContent();
      const highlights: TextHighlightRect[] = [];
      
      // Normalize the search text - take first 60 chars for better matching
      const searchText = anchorSnippet
        .substring(0, 60)
        .replace(/\s+/g, " ")
        .trim()
        .toLowerCase();
      
      if (!searchText || searchText.length < 10) return [];
      
      // Build a continuous text string and track item positions
      const items = textContent.items as Array<{
        str: string;
        transform: number[];
        width: number;
        height: number;
      }>;
      
      // Concatenate all text items to search across boundaries
      let fullText = "";
      const itemPositions: Array<{ start: number; end: number; itemIndex: number }> = [];
      
      items.forEach((item, index) => {
        const start = fullText.length;
        fullText += item.str;
        itemPositions.push({ start, end: fullText.length, itemIndex: index });
        // Add space between items for word boundaries
        fullText += " ";
      });
      
      const normalizedFullText = fullText.replace(/\s+/g, " ").toLowerCase();
      
      // Find the match position
      const matchIndex = normalizedFullText.indexOf(searchText);
      if (matchIndex === -1) return [];
      
      // Find which text items contain the match
      let charCount = 0;
      let inMatch = false;
      
      for (let i = 0; i < items.length; i++) {
        const item = items[i];
        const itemStart = charCount;
        const itemEnd = charCount + item.str.length + 1; // +1 for space
        
        // Check if this item overlaps with the match
        const matchEnd = matchIndex + searchText.length;
        const overlaps = itemStart < matchEnd && itemEnd > matchIndex;
        
        if (overlaps && item.str.trim()) {
          // Get position from transform matrix
          // transform = [scaleX, skewX, skewY, scaleY, translateX, translateY]
          const tx = item.transform[4];
          const ty = item.transform[5];
          const itemScaleY = Math.abs(item.transform[3]);
          
          // Convert to viewport coordinates
          const scaleX = viewport.width / (viewport.viewBox[2] - viewport.viewBox[0]);
          const scaleY = viewport.height / (viewport.viewBox[3] - viewport.viewBox[1]);
          
          const x = tx * scaleX;
          // PDF y=0 is at bottom, flip to top-left origin
          const pageHeight = viewport.viewBox[3] - viewport.viewBox[1];
          const y = (pageHeight - ty) * scaleY;
          
          // Calculate width and height
          const width = (item.width || item.str.length * 6) * scaleX;
          const height = (itemScaleY || 12) * scaleY;
          
          highlights.push({
            x: Math.max(0, x),
            y: Math.max(0, y - height), // Adjust for baseline
            width: Math.max(10, width),
            height: Math.max(10, height * 1.2), // Add some padding
          });
          
          inMatch = true;
        } else if (inMatch && !overlaps) {
          // Stop once we've passed the match
          break;
        }
        
        charCount = itemEnd;
      }
      
      return highlights;
    } catch (err) {
      console.error("Error finding text highlights:", err);
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
        
        // Jump to highlighted page if specified
        const targetPage = highlight?.page_no || 1;
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
  }, [url, open, highlight?.page_no]);

  // Draw bbox highlight overlay (only for precise highlights)
  const drawHighlight = useCallback((
    viewport: pdfjsLib.PageViewport,
    bbox: CitationHighlight["bbox"]
  ) => {
    if (!bbox || !highlightRef.current) return;

    // Use viewport.viewBox for accurate PDF coordinate transformation
    // viewBox = [x0, y0, x1, y1] in PDF points
    const pdfWidth = viewport.viewBox[2] - viewport.viewBox[0];
    const pdfHeight = viewport.viewBox[3] - viewport.viewBox[1];

    const scaleX = viewport.width / pdfWidth;
    const scaleY = viewport.height / pdfHeight;

    const x = bbox.x0 * scaleX;
    // Flip Y coordinate: PDF y=0 is at bottom, HTML y=0 is at top
    const y = (pdfHeight - bbox.y1) * scaleY;
    const width = (bbox.x1 - bbox.x0) * scaleX;
    const height = (bbox.y1 - bbox.y0) * scaleY;

    // Calculate what percentage of the page this covers
    const bboxWidth = bbox.x1 - bbox.x0;
    const bboxHeight = bbox.y1 - bbox.y0;
    const coveragePercent = (bboxWidth * bboxHeight) / (pdfWidth * pdfHeight) * 100;

    // Only show bbox highlight for precise regions (<50% coverage)
    if (coveragePercent <= 50) {
      highlightRef.current.style.left = `${x}px`;
      highlightRef.current.style.top = `${y}px`;
      highlightRef.current.style.width = `${width}px`;
      highlightRef.current.style.height = `${height}px`;
      highlightRef.current.style.background = "rgba(250, 204, 21, 0.35)";
      highlightRef.current.style.border = "2px solid rgb(234, 179, 8)";
      highlightRef.current.style.borderRadius = "4px";
      highlightRef.current.style.boxShadow = "0 0 0 4px rgba(250, 204, 21, 0.2)";
      highlightRef.current.style.display = "block";
    } else {
      highlightRef.current.style.display = "none";
    }
  }, []);

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
        setTextHighlights([]);
        if (highlightRef.current) {
          highlightRef.current.style.display = "none";
        }

        // Draw highlight if on current page
        if (highlight && highlight.page_no === currentPage) {
          if (highlight.bbox) {
            // Calculate bbox coverage using viewport dimensions
            const pdfWidth = viewport.viewBox[2] - viewport.viewBox[0];
            const pdfHeight = viewport.viewBox[3] - viewport.viewBox[1];
            const bboxWidth = highlight.bbox.x1 - highlight.bbox.x0;
            const bboxHeight = highlight.bbox.y1 - highlight.bbox.y0;
            const coveragePercent = (bboxWidth * bboxHeight) / (pdfWidth * pdfHeight) * 100;

            if (coveragePercent <= 50) {
              // Precise bbox - use coordinate-based highlighting
              drawHighlight(viewport, highlight.bbox);
            } else if (highlight.anchor_snippet) {
              // Large bbox - fall back to text search highlighting
              const highlights = await findTextHighlights(page, viewport, highlight.anchor_snippet);
              setTextHighlights(highlights);
            }
          } else if (highlight.anchor_snippet) {
            // No bbox but have anchor_snippet - use text search
            const highlights = await findTextHighlights(page, viewport, highlight.anchor_snippet);
            setTextHighlights(highlights);
          }
        }
      } catch (err) {
        console.error("Failed to render page:", err);
      }
    };

    renderPage();
  }, [pdf, currentPage, scale, highlight, findTextHighlights, drawHighlight]);
  
  // Text search using anchor_snippet (fallback for page navigation)
  useEffect(() => {
    if (!highlight?.anchor_snippet || !pdf || highlight.bbox) return;
    
    const searchForSnippet = async () => {
      const snippet = highlight.anchor_snippet!.substring(0, 50).toLowerCase();
      
      for (let i = 1; i <= numPages; i++) {
        const page = await pdf.getPage(i);
        const textContent = await page.getTextContent();
        const text = textContent.items
          .map((item) => (item as PDFTextContentItem).str ?? "")
          .join(" ")
          .toLowerCase();
        
        if (text.includes(snippet)) {
          setCurrentPage(i);
          setPageInput(String(i));
          break;
        }
      }
    };
    
    searchForSnippet();
  }, [highlight, pdf, numPages]);
  
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
  
  // Jump to citation
  const jumpToCitation = () => {
    if (highlight?.page_no) {
      setCurrentPage(highlight.page_no);
      setPageInput(String(highlight.page_no));
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
    if (!highlight) return null;

    if (highlight.bbox) {
      return (
        <Badge variant="secondary" className="bg-yellow-500/10 text-yellow-600 dark:text-yellow-400 border-yellow-500/30">
          <Target className="h-3 w-3 mr-1" />
          Highlighted
        </Badge>
      );
    }

    if (highlight.anchor_snippet) {
      return (
        <Badge variant="secondary" className="bg-orange-500/10 text-orange-600 dark:text-orange-400 border-orange-500/30">
          <MapPin className="h-3 w-3 mr-1" />
          Text Match
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
          {highlight && (
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
                      <span className="hidden sm:inline">Page {highlight.page_no}</span>
                      <span className="sm:hidden">{highlight.page_no}</span>
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
                <canvas
                  ref={canvasRef}
                  className="shadow-xl rounded-sm bg-white"
                  style={{ maxWidth: "100%" }}
                />
                {/* Bbox highlight overlay - for precise coordinates */}
                <div
                  ref={highlightRef}
                  className="absolute pointer-events-none transition-all duration-300"
                  style={{ display: "none" }}
                />
                {/* Text search highlight overlays - for matching anchor_snippet */}
                {textHighlights.map((rect, i) => (
                  <div
                    key={i}
                    className="absolute pointer-events-none bg-yellow-400/50 border-2 border-yellow-500 rounded-sm shadow-lg z-10"
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
              {highlight && currentPage === highlight.page_no && " • Viewing citation source"}
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

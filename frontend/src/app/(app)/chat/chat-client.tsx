"use client";

import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Send,
  FileText,
  Loader2,
  AlertTriangle,
  ChevronRight,
  BookOpen,
  Clock,
  Sparkles,
  Copy,
  Check,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import { toast } from "sonner";

import { cn, formatDuration, generateId, getFilename } from "@/lib/utils";
import { askQuestion, listDocuments } from "@/lib/api";
import type { AskResponse, Citation, Conflict } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
  TooltipProvider,
} from "@/components/ui/tooltip";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { PDFViewer, CitationHighlight } from "@/components/pdf-viewer";

// Helper to parse inline citations like [seed:14] and render them as clickable chips
function parseInlineCitations(
  content: string,
  citations: Citation[] | undefined,
  onCitationClick?: (citation: Citation) => void
): React.ReactNode {
  // Pattern matches [seed:14], [seed:15], etc.
  const citationPattern = /\[seed:(\d+)\]/g;
  const parts: React.ReactNode[] = [];
  let lastIndex = 0;
  let match;
  let key = 0;

  while ((match = citationPattern.exec(content)) !== null) {
    // Add text before the citation
    if (match.index > lastIndex) {
      parts.push(
        <span key={`text-${key++}`} className="inline">
          <ReactMarkdown>
            {content.slice(lastIndex, match.index)}
          </ReactMarkdown>
        </span>
      );
    }

    const pageNo = parseInt(match[1], 10);
    
    // Find matching citation by page number
    const citation = citations?.find(c => c.page_no === pageNo);
    
    if (citation && onCitationClick) {
      // Render as inline clickable chip
      parts.push(
        <button
          key={`cite-${key++}`}
          onClick={() => onCitationClick(citation)}
          className="inline-flex items-center gap-1 px-1.5 py-0.5 mx-0.5 text-xs font-medium bg-primary/10 text-primary hover:bg-primary/20 rounded border border-primary/20 transition-colors cursor-pointer align-baseline"
          title={`View source: Page ${pageNo}`}
        >
          <FileText className="h-3 w-3" />
          <span>p.{pageNo}</span>
        </button>
      );
    } else {
      // No matching citation, render as static badge
      parts.push(
        <span
          key={`cite-${key++}`}
          className="inline-flex items-center gap-1 px-1.5 py-0.5 mx-0.5 text-xs font-medium bg-muted text-muted-foreground rounded align-baseline"
        >
          p.{pageNo}
        </span>
      );
    }

    lastIndex = match.index + match[0].length;
  }

  // Add remaining text after the last citation
  if (lastIndex < content.length) {
    parts.push(
      <span key={`text-${key++}`} className="inline">
        <ReactMarkdown>
          {content.slice(lastIndex)}
        </ReactMarkdown>
      </span>
    );
  }

  // If no citations found, just return the original content
  if (parts.length === 0) {
    return <ReactMarkdown>{content}</ReactMarkdown>;
  }

  return <>{parts}</>;
}

// Message types
interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: Date;
  response?: AskResponse;
  isLoading?: boolean;
  error?: string;
}

// Citation chip component
function CitationChip({ citation, onClick }: { citation: Citation; onClick?: () => void }) {
  const label = citation.label || `Page ${citation.page_no || "?"}`;
  
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          onClick={onClick}
          className="citation-chip"
        >
          <BookOpen className="h-3 w-3" />
          {label}
        </button>
      </TooltipTrigger>
      <TooltipContent side="top" className="max-w-xs">
        <p className="text-xs">
          {citation.text?.slice(0, 150)}
          {citation.text && citation.text.length > 150 ? "..." : ""}
        </p>
      </TooltipContent>
    </Tooltip>
  );
}

// Conflict warning component
function ConflictWarning({ conflicts }: { conflicts: Conflict[] }) {
  const [isOpen, setIsOpen] = React.useState(false);
  
  return (
    <Collapsible open={isOpen} onOpenChange={setIsOpen}>
      <CollapsibleTrigger asChild>
        <Button
          variant="ghost"
          size="sm"
          className="gap-2 text-amber-500 hover:text-amber-600"
        >
          <AlertTriangle className="h-4 w-4" />
          {conflicts.length} potential conflict{conflicts.length > 1 ? "s" : ""}
          <ChevronRight
            className={cn("h-4 w-4 transition-transform", isOpen && "rotate-90")}
          />
        </Button>
      </CollapsibleTrigger>
      <CollapsibleContent className="mt-2 space-y-2">
        {conflicts.map((conflict, i) => (
          <div
            key={i}
            className="rounded-md border border-amber-200 bg-amber-50 dark:border-amber-900 dark:bg-amber-950 p-3 text-sm"
          >
            <p className="text-amber-800 dark:text-amber-200">
              {conflict.description}
            </p>
            {conflict.source && (
              <p className="mt-1 text-xs text-amber-600 dark:text-amber-400">
                Source: {conflict.source}
              </p>
            )}
          </div>
        ))}
      </CollapsibleContent>
    </Collapsible>
  );
}

// Score indicator component
function ScoreIndicator({ score, showLabel = true }: { score: number; showLabel?: boolean }) {
  // Convert score (0-1) to percentage and color
  const percentage = Math.round(score * 100);
  const getColor = () => {
    if (percentage >= 70) return "bg-emerald-500";
    if (percentage >= 50) return "bg-amber-500";
    return "bg-rose-500";
  };
  
  return (
    <div className="flex items-center gap-2">
      <div className="w-16 h-1.5 bg-muted rounded-full overflow-hidden">
        <div 
          className={cn("h-full rounded-full transition-all", getColor())}
          style={{ width: `${percentage}%` }}
        />
      </div>
      {showLabel && (
        <span className="text-xs font-medium tabular-nums text-muted-foreground">
          {percentage}%
        </span>
      )}
    </div>
  );
}

// Timing bar component
function TimingBar({ 
  label, 
  value, 
  total, 
  color = "bg-primary" 
}: { 
  label: string; 
  value: number; 
  total: number; 
  color?: string;
}) {
  const percentage = total > 0 ? (value / total) * 100 : 0;
  const formattedValue = value >= 1000 
    ? `${(value / 1000).toFixed(2)}s` 
    : `${Math.round(value)}ms`;
  
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-xs">
        <span className="text-muted-foreground">{label}</span>
        <span className="font-mono font-medium">{formattedValue}</span>
      </div>
      <div className="h-1.5 bg-muted rounded-full overflow-hidden">
        <div 
          className={cn("h-full rounded-full transition-all duration-500", color)}
          style={{ width: `${Math.max(percentage, 2)}%` }}
        />
      </div>
    </div>
  );
}

// Node card component
function NodeCard({ 
  node, 
  type,
  index,
}: { 
  node: { 
    page_no?: number; 
    score?: number; 
    text?: string;
    relationship?: string;
    label?: string;
  }; 
  type: "seed" | "expanded";
  index: number;
}) {
  const [isExpanded, setIsExpanded] = React.useState(false);
  const hasText = node.text && node.text.length > 0;
  const truncatedText = node.text?.slice(0, 150);
  const needsTruncation = node.text && node.text.length > 150;
  
  return (
    <div 
      className={cn(
        "group relative rounded-lg border bg-card transition-all duration-200",
        "hover:border-primary/50 hover:shadow-sm",
        isExpanded && "ring-1 ring-primary/20"
      )}
    >
      {/* Header */}
      <div className="flex items-center gap-3 p-3">
        {/* Index badge */}
        <div className={cn(
          "flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-xs font-semibold",
          type === "seed" 
            ? "bg-primary/10 text-primary" 
            : "bg-muted text-muted-foreground"
        )}>
          {index + 1}
        </div>
        
        {/* Info */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            {node.page_no && (
              <Badge variant="secondary" className="text-xs font-medium">
                <FileText className="h-3 w-3 mr-1" />
                Page {node.page_no}
              </Badge>
            )}
            {type === "expanded" && node.relationship && (
              <Badge variant="outline" className="text-xs capitalize">
                {node.relationship.replace(/_/g, " ")}
              </Badge>
            )}
            {node.label && (
              <span className="text-xs text-muted-foreground truncate">
                {node.label}
              </span>
            )}
          </div>
        </div>
        
        {/* Score for seed nodes */}
        {type === "seed" && typeof node.score === "number" && (
          <div className="shrink-0">
            <ScoreIndicator score={node.score} />
          </div>
        )}
      </div>
      
      {/* Text preview */}
      {hasText && (
        <div className="px-3 pb-3">
          <p className={cn(
            "text-xs text-muted-foreground leading-relaxed",
            !isExpanded && "line-clamp-2"
          )}>
            {isExpanded ? node.text : truncatedText}
            {!isExpanded && needsTruncation && "..."}
          </p>
          {needsTruncation && (
            <button
              onClick={() => setIsExpanded(!isExpanded)}
              className="text-xs text-primary hover:underline mt-1 font-medium"
            >
              {isExpanded ? "Show less" : "Show more"}
            </button>
          )}
        </div>
      )}
    </div>
  );
}

// Source panel component
function SourcePanel({ response }: { response: AskResponse }) {
  const [seedsOpen, setSeedsOpen] = React.useState(true);
  const [expandedOpen, setExpandedOpen] = React.useState(false);
  
  const timing = response.timing || {};
  const totalMs = timing.total_ms || 0;
  
  // Calculate timing phases for the visualization
  const timingPhases = [
    { label: "Embedding", value: timing.embedding_ms || 0, color: "bg-blue-500" },
    { label: "Search", value: timing.search_ms || 0, color: "bg-violet-500" },
    { label: "Expansion", value: timing.expansion_ms || 0, color: "bg-amber-500" },
    { label: "Generation", value: timing.generation_ms || 0, color: "bg-emerald-500" },
  ].filter(p => p.value > 0);
  
  return (
    <div className="space-y-6 pr-2">
      {/* Summary cards */}
      <div className="grid grid-cols-3 gap-3">
        <div className="rounded-lg border bg-card p-3 text-center">
          <div className="text-2xl font-bold text-primary">
            {response.seed_nodes?.length || 0}
          </div>
          <div className="text-xs text-muted-foreground mt-1">Seeds Found</div>
        </div>
        <div className="rounded-lg border bg-card p-3 text-center">
          <div className="text-2xl font-bold text-primary">
            {response.expanded_nodes?.length || 0}
          </div>
          <div className="text-xs text-muted-foreground mt-1">Expanded</div>
        </div>
        <div className="rounded-lg border bg-card p-3 text-center">
          <div className="text-2xl font-bold text-primary">
            {response.total_context_tokens?.toLocaleString() || 0}
          </div>
          <div className="text-xs text-muted-foreground mt-1">Tokens</div>
        </div>
      </div>

      {/* Timing breakdown */}
      <div className="rounded-lg border bg-card p-4">
        <div className="flex items-center justify-between mb-4">
          <h4 className="text-sm font-semibold flex items-center gap-2">
            <Clock className="h-4 w-4 text-primary" />
            Performance
          </h4>
          <Badge variant="outline" className="font-mono">
            {totalMs >= 1000 
              ? `${(totalMs / 1000).toFixed(2)}s total` 
              : `${Math.round(totalMs)}ms total`}
          </Badge>
        </div>
        
        {/* Stacked bar */}
        <div className="h-3 bg-muted rounded-full overflow-hidden flex mb-4">
          {timingPhases.map((phase, i) => (
            <div
              key={i}
              className={cn("h-full transition-all duration-500", phase.color)}
              style={{ width: `${(phase.value / totalMs) * 100}%` }}
              title={`${phase.label}: ${phase.value.toFixed(0)}ms`}
            />
          ))}
        </div>
        
        {/* Legend */}
        <div className="grid grid-cols-2 gap-3">
          {timingPhases.map((phase, i) => (
            <div key={i} className="flex items-center gap-2 text-xs">
              <div className={cn("h-2 w-2 rounded-full", phase.color)} />
              <span className="text-muted-foreground flex-1">{phase.label}</span>
              <span className="font-mono font-medium">
                {phase.value >= 1000 
                  ? `${(phase.value / 1000).toFixed(1)}s` 
                  : `${Math.round(phase.value)}ms`}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Seed nodes */}
      {response.seed_nodes && response.seed_nodes.length > 0 && (
        <Collapsible open={seedsOpen} onOpenChange={setSeedsOpen}>
          <CollapsibleTrigger asChild>
            <button className="flex items-center justify-between w-full text-left p-3 rounded-lg border bg-card hover:bg-accent transition-colors">
              <div className="flex items-center gap-2">
                <div className="h-8 w-8 rounded-md bg-primary/10 flex items-center justify-center">
                  <Sparkles className="h-4 w-4 text-primary" />
                </div>
                <div>
                  <h4 className="text-sm font-semibold">Retrieved Chunks</h4>
                  <p className="text-xs text-muted-foreground">
                    {response.seed_nodes.length} most relevant passages
                  </p>
                </div>
              </div>
              <ChevronRight className={cn(
                "h-4 w-4 text-muted-foreground transition-transform duration-200",
                seedsOpen && "rotate-90"
              )} />
            </button>
          </CollapsibleTrigger>
          <CollapsibleContent className="pt-3">
            <div className="space-y-2">
              {response.seed_nodes.map((node, i) => (
                <NodeCard key={i} node={node} type="seed" index={i} />
              ))}
            </div>
          </CollapsibleContent>
        </Collapsible>
      )}

      {/* Expanded nodes */}
      {response.expanded_nodes && response.expanded_nodes.length > 0 && (
        <Collapsible open={expandedOpen} onOpenChange={setExpandedOpen}>
          <CollapsibleTrigger asChild>
            <button className="flex items-center justify-between w-full text-left p-3 rounded-lg border bg-card hover:bg-accent transition-colors">
              <div className="flex items-center gap-2">
                <div className="h-8 w-8 rounded-md bg-muted flex items-center justify-center">
                  <ChevronRight className="h-4 w-4 text-muted-foreground" />
                </div>
                <div>
                  <h4 className="text-sm font-semibold">Expanded Context</h4>
                  <p className="text-xs text-muted-foreground">
                    {response.expanded_nodes.length} related passages via graph traversal
                  </p>
                </div>
              </div>
              <ChevronRight className={cn(
                "h-4 w-4 text-muted-foreground transition-transform duration-200",
                expandedOpen && "rotate-90"
              )} />
            </button>
          </CollapsibleTrigger>
          <CollapsibleContent className="pt-3">
            <div className="space-y-2">
              {response.expanded_nodes.map((node, i) => (
                <NodeCard key={i} node={node} type="expanded" index={i} />
              ))}
            </div>
          </CollapsibleContent>
        </Collapsible>
      )}

      {/* Model info */}
      <div className="rounded-lg border bg-card p-4">
        <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">
          Model
        </h4>
        <p className="text-sm font-mono">{response.model_id || "Unknown"}</p>
      </div>
    </div>
  );
}

// Chat message component
function ChatMessage({
  message,
  onSourceClick,
  onCitationClick,
}: {
  message: Message;
  onSourceClick?: () => void;
  onCitationClick?: (citation: Citation) => void;
}) {
  const [copied, setCopied] = React.useState(false);
  
  const handleCopy = async () => {
    await navigator.clipboard.writeText(message.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div
      className={cn(
        "flex gap-4",
        message.role === "user" ? "justify-end" : "justify-start"
      )}
    >
      {message.role === "assistant" && (
        <div className="bg-primary text-primary-foreground p-2 rounded-lg h-fit">
          <Sparkles className="h-4 w-4" />
        </div>
      )}
      
      <div
        className={cn(
          "max-w-[80%] rounded-lg p-4",
          message.role === "user"
            ? "bg-primary text-primary-foreground"
            : "bg-muted"
        )}
      >
        {message.isLoading ? (
          <div className="flex items-center gap-2">
            <Loader2 className="h-4 w-4 animate-spin" />
            <span className="text-sm">Thinking...</span>
          </div>
        ) : message.error ? (
          <div className="flex items-center gap-2 text-destructive">
            <AlertTriangle className="h-4 w-4" />
            <span className="text-sm">{message.error}</span>
          </div>
        ) : (
          <>
            {/* Query Rewrite Indicator - collapsible */}
            {message.role === "assistant" && message.response?.llm_rewrite && message.response.llm_rewrite.used_llm && (
              <details className="mb-3 group rounded-lg bg-gradient-to-r from-blue-500/10 to-purple-500/10 border border-blue-500/30 overflow-hidden">
                <summary className="cursor-pointer list-none w-full flex items-center gap-2 p-2 text-sm hover:from-blue-500/15 hover:to-purple-500/15 transition-colors">
                  <Sparkles className="h-3.5 w-3.5 text-blue-500 flex-shrink-0" />
                  <span className="font-medium text-blue-600 dark:text-blue-400 text-xs">Query Rewritten</span>
                  <Badge variant="outline" className="text-[10px] bg-blue-500/10 border-blue-500/30 py-0">
                    Context-Aware
                  </Badge>
                  <ChevronRight className="h-3.5 w-3.5 text-blue-500 ml-auto transition-transform duration-200 group-open:rotate-90" />
                </summary>
                <div className="px-2 pb-2 border-t border-blue-500/20 pt-2 mx-2 mb-1">
                  <div className="grid grid-cols-[auto_1fr] gap-x-2 gap-y-1 text-xs pl-5">
                    <span className="text-muted-foreground font-medium">Original:</span>
                    <span className="italic text-muted-foreground">&quot;{message.response.original_question || message.response.llm_rewrite.original_query}&quot;</span>
                    <span className="text-muted-foreground font-medium">Searched:</span>
                    <span className="font-medium">&quot;{message.response.llm_rewrite.rewritten_query}&quot;</span>
                  </div>
                </div>
              </details>
            )}
            
            <div className="prose prose-sm dark:prose-invert max-w-none">
              {message.role === "assistant" && message.response?.citations ? (
                // Parse inline [seed:X] citations and render as clickable chips
                parseInlineCitations(
                  message.content,
                  message.response.citations,
                  onCitationClick
                )
              ) : (
                <ReactMarkdown>{message.content}</ReactMarkdown>
              )}
            </div>
            
            {message.role === "assistant" && message.response && (
              <div className="mt-4 space-y-3">
                {/* Citations */}
                {message.response.citations && message.response.citations.length > 0 && (
                  <div className="flex flex-wrap gap-2">
                    {message.response.citations.map((citation, i) => (
                      <CitationChip
                        key={i}
                        citation={citation}
                        onClick={() => onCitationClick?.(citation)}
                      />
                    ))}
                  </div>
                )}
                
                {/* Conflicts */}
                {message.response.conflicts && message.response.conflicts.length > 0 && (
                  <ConflictWarning conflicts={message.response.conflicts} />
                )}
                
                {/* Actions */}
                <div className="flex items-center gap-2 pt-2 border-t">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={handleCopy}
                    className="gap-2"
                  >
                    {copied ? (
                      <Check className="h-3 w-3" />
                    ) : (
                      <Copy className="h-3 w-3" />
                    )}
                    {copied ? "Copied" : "Copy"}
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={onSourceClick}
                    className="gap-2"
                  >
                    <BookOpen className="h-3 w-3" />
                    View Sources
                  </Button>
                </div>
              </div>
            )}
          </>
        )}
      </div>
      
      {message.role === "user" && (
        <div className="bg-muted p-2 rounded-lg h-fit">
          <span className="text-xs font-medium">You</span>
        </div>
      )}
    </div>
  );
}

export default function ChatClient() {
  const [messages, setMessages] = React.useState<Message[]>([]);
  const [input, setInput] = React.useState("");
  const [isLoading, setIsLoading] = React.useState(false);
  const [selectedDoc, setSelectedDoc] = React.useState<string>("__all__"); // Default to all documents
  const [selectedResponse, setSelectedResponse] = React.useState<AskResponse | null>(null);
  const [sourceSheetOpen, setSourceSheetOpen] = React.useState(false);
  const scrollRef = React.useRef<HTMLDivElement>(null);
  const inputRef = React.useRef<HTMLTextAreaElement>(null);
  
  // PDF Viewer state for citation highlighting
  const [pdfViewerOpen, setPdfViewerOpen] = React.useState(false);
  const [pdfViewerUrl, setPdfViewerUrl] = React.useState("");
  const [pdfViewerHighlight, setPdfViewerHighlight] = React.useState<CitationHighlight | undefined>();
  const [pdfViewerTitle, setPdfViewerTitle] = React.useState("");

  // Fetch documents for the selector
  const { data: docsData, isLoading: docsLoading } = useQuery({
    queryKey: ["documents-for-chat"],
    queryFn: () => listDocuments({ limit: 100 }),
  });

  const documents = docsData?.items || [];

  // Auto-scroll to bottom
  React.useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  // Focus input on mount
  React.useEffect(() => {
    inputRef.current?.focus();
  }, []);

  // Handle citation click to open PDF viewer with highlighting
  const handleCitationClick = React.useCallback((citation: Citation, docId: string) => {
    // Get API base URL
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    
    // Use raw_url from citation or construct it
    const pdfUrl = citation.raw_url 
      ? `${apiUrl}${citation.raw_url}`
      : `${apiUrl}/v1/documents/${docId}/raw`;
    
    // Build highlight info
    const highlight: CitationHighlight = {
      page_no: citation.page_no || 1,
      bbox: citation.bbox,
      page_size: citation.page_size,
      anchor_snippet: citation.anchor_snippet || citation.text,
      label: citation.label,
    };
    
    // Find document name for title
    const doc = documents.find((d) => d.doc_id === docId);
    const title = doc ? getFilename(doc.source_uri) : "Document";
    
    setPdfViewerUrl(pdfUrl);
    setPdfViewerHighlight(highlight);
    setPdfViewerTitle(title);
    setPdfViewerOpen(true);
  }, [documents]);

  const handleSubmit = async (e?: React.FormEvent) => {
    e?.preventDefault();
    
    const trimmedInput = input.trim();
    if (!trimmedInput || isLoading) return;

    // Add user message
    const userMessage: Message = {
      id: generateId(),
      role: "user",
      content: trimmedInput,
      timestamp: new Date(),
    };

    // Add loading message
    const loadingMessage: Message = {
      id: generateId(),
      role: "assistant",
      content: "",
      timestamp: new Date(),
      isLoading: true,
    };

    setMessages((prev) => [...prev, userMessage, loadingMessage]);
    setInput("");
    setIsLoading(true);

    try {
      // Build chat history from previous messages (excluding the current ones just added)
      const chatHistory = messages
        .filter(m => !m.isLoading && !m.error && m.content)
        .map(m => ({
          role: m.role as "user" | "assistant",
          content: m.content,
        }));
      
      // Build request - don't send doc_id if "All Documents" is selected
      const request: Parameters<typeof askQuestion>[0] = {
        question: trimmedInput,
        top_k: 5,
        mode: "standard",
        chat_history: chatHistory.length > 0 ? chatHistory : undefined,
      };
      if (selectedDoc && selectedDoc !== "__all__") {
        request.doc_id = selectedDoc;
      }
      
      const response = await askQuestion(request);

      // Update loading message with response
      setMessages((prev) =>
        prev.map((msg) =>
          msg.id === loadingMessage.id
            ? {
                ...msg,
                content: response.answer,
                isLoading: false,
                response,
              }
            : msg
        )
      );

      // Check for errors in response
      if (!response.success && response.error) {
        toast.error(response.error);
      }
    } catch (error) {
      console.error("Chat error:", error);
      const errorMessage = error instanceof Error ? error.message : "Failed to get response";
      
      // Update loading message with error
      setMessages((prev) =>
        prev.map((msg) =>
          msg.id === loadingMessage.id
            ? {
                ...msg,
                content: "",
                isLoading: false,
                error: errorMessage,
              }
            : msg
        )
      );

      toast.error(errorMessage);
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const openSourcePanel = (response: AskResponse) => {
    setSelectedResponse(response);
    setSourceSheetOpen(true);
  };

  return (
    <TooltipProvider>
    <div className="flex flex-col h-[calc(100vh-3.5rem)]">
      {/* Chat header */}
      <div className="flex items-center justify-between px-4 py-3 border-b">
        <div className="flex items-center gap-3">
          <Select value={selectedDoc} onValueChange={setSelectedDoc} disabled={docsLoading}>
            <SelectTrigger className="w-[300px]">
              <FileText className="h-4 w-4 mr-2" />
              <SelectValue placeholder={docsLoading ? "Loading documents..." : "Select document"} />
            </SelectTrigger>
            <SelectContent>
              {docsLoading ? (
                <SelectItem value="__loading__" disabled>Loading...</SelectItem>
              ) : (
                <>
                  <SelectItem value="__all__">
                    <div className="flex items-center gap-2">
                      <span>All Documents</span>
                      <Badge variant="secondary" className="text-xs">
                        {documents.length}
                      </Badge>
                    </div>
                  </SelectItem>
                  {documents.length > 0 && (
                    <div className="border-t my-1" />
                  )}
                  {documents.map((doc) => (
                    <SelectItem key={doc.doc_id} value={doc.doc_id}>
                      <div className="flex items-center gap-2">
                        <span>{getFilename(doc.source_uri)}</span>
                        {doc.doc_type && (
                          <Badge variant="outline" className="text-xs">
                            {doc.doc_type}
                          </Badge>
                        )}
                      </div>
                    </SelectItem>
                  ))}
                </>
              )}
            </SelectContent>
          </Select>
        </div>

        <div className="flex items-center gap-2">
          <Sheet open={sourceSheetOpen} onOpenChange={setSourceSheetOpen}>
            <SheetTrigger asChild>
              <Button variant="outline" size="sm" disabled={!selectedResponse}>
                <BookOpen className="h-4 w-4 mr-2" />
                Sources
              </Button>
            </SheetTrigger>
            <SheetContent className="w-[400px] sm:w-[540px]">
              <SheetHeader>
                <SheetTitle>Source Details</SheetTitle>
              </SheetHeader>
              <ScrollArea className="h-[calc(100vh-8rem)] mt-4">
                {selectedResponse && <SourcePanel response={selectedResponse} />}
              </ScrollArea>
            </SheetContent>
          </Sheet>
        </div>
      </div>

      {/* Messages area */}
      <ScrollArea ref={scrollRef} className="flex-1 p-4">
        <div className="max-w-3xl mx-auto space-y-6">
          {messages.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-20 text-center">
              <div className="bg-primary/10 p-4 rounded-full mb-4">
                <Sparkles className="h-8 w-8 text-primary" />
              </div>
              <h2 className="text-xl font-semibold mb-2">Have a conversation with our FDD</h2>
              <p className="text-muted-foreground max-w-md">
                Ask questions about the 2025 FDD - All States except CA, HI, IL, IN, MD, MN, NY, ND, SD, VA, WA.pdf. 
                I&apos;ll provide answers with citations to the relevant sections.
              </p>
            </div>
          ) : (
            messages.map((message) => (
              <ChatMessage
                key={message.id}
                message={message}
                onSourceClick={() =>
                  message.response && openSourcePanel(message.response)
                }
                onCitationClick={(citation) => {
                  // Open PDF viewer with citation highlighting
                  const docId = message.response?.doc_id || selectedDoc;
                  handleCitationClick(citation, docId);
                }}
              />
            ))
          )}
        </div>
      </ScrollArea>

      {/* Input area */}
      <div className="border-t p-4">
        <form onSubmit={handleSubmit} className="max-w-3xl mx-auto">
          <div className="relative">
            <Textarea
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={selectedDoc === "__all__" ? "Ask a question across all documents..." : "Ask a question about the selected document..."}
              className="min-h-[80px] resize-none pr-12"
              disabled={isLoading}
            />
            <Button
              type="submit"
              size="icon"
              className="absolute bottom-2 right-2"
              disabled={!input.trim() || isLoading}
            >
              {isLoading ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Send className="h-4 w-4" />
              )}
            </Button>
          </div>
          <div className="flex items-center justify-center gap-3 mt-2">
            <p className="text-xs text-muted-foreground">
              Press Enter to send, Shift+Enter for new line
            </p>
            {messages.length > 0 && (
              <div className="flex items-center gap-1.5 text-xs text-blue-600 dark:text-blue-400">
                <Sparkles className="h-3 w-3" />
                <span>Context-aware rewriting enabled</span>
              </div>
            )}
          </div>
        </form>
      </div>
    </div>
    
    {/* PDF Viewer for citation highlighting */}
    <PDFViewer
      url={pdfViewerUrl}
      open={pdfViewerOpen}
      onClose={() => setPdfViewerOpen(false)}
      highlight={pdfViewerHighlight}
      title={pdfViewerTitle}
    />
    </TooltipProvider>
  );
}

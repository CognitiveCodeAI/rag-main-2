"use client";

import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import {
  FileText,
  Code2,
  Search as SearchIcon,
  MessageSquare,
  Braces,
  Copy,
  Check,
  ChevronRight,
  Tag,
  Sparkles,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { listPrompts, getPrompt, PromptMetadata, PromptDetail, PromptListResponse } from "@/lib/api";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

// Category icons mapping
const categoryIcons: Record<string, React.ElementType> = {
  qa_pipeline: MessageSquare,
  query_processing: SearchIcon,
  ocr: FileText,
  utilities: Braces,
};

// ============================================
// Prompt List Component (Left Panel)
// ============================================

interface PromptListProps {
  prompts: PromptListResponse | undefined;
  isLoading: boolean;
  selected: string | null;
  onSelect: (name: string) => void;
}

function PromptList({ prompts, isLoading, selected, onSelect }: PromptListProps) {
  return (
    <Card className="w-80 flex-shrink-0 flex flex-col">
      <CardHeader className="pb-3">
        <CardTitle className="text-base flex items-center gap-2">
          <Sparkles className="h-4 w-4" />
          Available Prompts
        </CardTitle>
        <CardDescription>
          {prompts?.prompts.length || 0} prompt templates
        </CardDescription>
      </CardHeader>
      <CardContent className="p-0 flex-1 overflow-hidden">
        <ScrollArea className="h-full">
          {isLoading ? (
            <div className="space-y-2 p-4">
              {[...Array(8)].map((_, i) => (
                <Skeleton key={i} className="h-12 w-full" />
              ))}
            </div>
          ) : (
            <div className="space-y-4 p-4">
              {Object.entries(prompts?.categories || {}).map(([categoryKey, categoryLabel]) => {
                const Icon = categoryIcons[categoryKey] || Code2;
                const categoryPrompts = prompts?.prompts.filter(p => p.category === categoryKey) || [];

                if (categoryPrompts.length === 0) return null;

                return (
                  <div key={categoryKey}>
                    <div className="flex items-center gap-2 mb-2 text-sm font-medium text-muted-foreground">
                      <Icon className="h-4 w-4" />
                      {categoryLabel}
                    </div>
                    <div className="space-y-1">
                      {categoryPrompts.map(prompt => (
                        <Button
                          key={prompt.name}
                          variant={selected === prompt.name ? "secondary" : "ghost"}
                          className={cn(
                            "w-full justify-start h-auto py-2.5 px-3",
                            selected === prompt.name && "bg-secondary"
                          )}
                          onClick={() => onSelect(prompt.name)}
                        >
                          <div className="flex items-center gap-2 w-full">
                            <Code2 className="h-4 w-4 shrink-0 text-muted-foreground" />
                            <span className="truncate flex-1 text-left capitalize">
                              {prompt.name.replace(/_/g, " ")}
                            </span>
                            <Badge variant="outline" className="text-xs shrink-0">
                              {prompt.version}
                            </Badge>
                            <ChevronRight className={cn(
                              "h-4 w-4 shrink-0 transition-transform",
                              selected === prompt.name ? "text-foreground" : "text-muted-foreground/50"
                            )} />
                          </div>
                        </Button>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </ScrollArea>
      </CardContent>
    </Card>
  );
}

// ============================================
// Prompt Content with Variable Highlighting
// ============================================

interface PromptContentProps {
  content: string;
}

function PromptContent({ content }: PromptContentProps) {
  // Highlight template variables like {question}, {context}
  const highlightedContent = React.useMemo(() => {
    // Split on template variables, keeping the delimiters
    const parts = content.split(/(\{[^}]+\})/g);
    return parts.map((part, i) => {
      if (part.match(/^\{[^}]+\}$/)) {
        return (
          <span
            key={i}
            className="bg-amber-500/20 text-amber-700 dark:text-amber-400 px-1 rounded font-semibold"
          >
            {part}
          </span>
        );
      }
      return part;
    });
  }, [content]);

  return (
    <pre className="p-4 text-sm font-mono whitespace-pre-wrap leading-relaxed text-foreground/90">
      {highlightedContent}
    </pre>
  );
}

// ============================================
// Prompt Detail Component (Right Panel)
// ============================================

interface PromptDetailPanelProps {
  prompt: PromptDetail | undefined;
  isLoading: boolean;
  hasSelection: boolean;
  onVersionChange: (version: string) => void;
}

function PromptDetailPanel({ prompt, isLoading, hasSelection, onVersionChange }: PromptDetailPanelProps) {
  const [copied, setCopied] = React.useState(false);

  const handleCopy = async () => {
    if (prompt?.content) {
      await navigator.clipboard.writeText(prompt.content);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  if (!hasSelection) {
    return (
      <Card className="flex-1 flex items-center justify-center">
        <div className="text-center">
          <div className="mx-auto w-16 h-16 rounded-full bg-muted flex items-center justify-center mb-4">
            <Code2 className="h-8 w-8 text-muted-foreground" />
          </div>
          <h3 className="font-semibold text-lg">Select a Prompt</h3>
          <p className="text-sm text-muted-foreground mt-1">
            Choose a prompt from the list to view its content
          </p>
        </div>
      </Card>
    );
  }

  if (isLoading) {
    return (
      <Card className="flex-1 flex flex-col overflow-hidden">
        <CardHeader className="flex-shrink-0 pb-3">
          <Skeleton className="h-6 w-48" />
          <Skeleton className="h-4 w-32 mt-2" />
        </CardHeader>
        <Separator />
        <CardContent className="flex-1 p-4">
          <div className="space-y-2">
            {[...Array(12)].map((_, i) => (
              <Skeleton key={i} className="h-4 w-full" />
            ))}
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="flex-1 flex flex-col overflow-hidden">
      <CardHeader className="flex-shrink-0 pb-3">
        <div className="flex items-start justify-between">
          <div>
            <CardTitle className="capitalize text-xl">
              {prompt?.name.replace(/_/g, " ") || "Loading..."}
            </CardTitle>
            <CardDescription className="flex items-center gap-2 mt-1.5">
              <Badge>{prompt?.version}</Badge>
              <span className="text-muted-foreground">{prompt?.category_label}</span>
            </CardDescription>
          </div>
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button variant="outline" size="icon" onClick={handleCopy}>
                  {copied ? (
                    <Check className="h-4 w-4 text-green-500" />
                  ) : (
                    <Copy className="h-4 w-4" />
                  )}
                </Button>
              </TooltipTrigger>
              <TooltipContent>
                {copied ? "Copied!" : "Copy to clipboard"}
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        </div>

        {/* Template Variables */}
        {prompt?.template_variables && prompt.template_variables.length > 0 && (
          <div className="flex items-center gap-2 mt-4 flex-wrap">
            <Tag className="h-4 w-4 text-muted-foreground shrink-0" />
            <span className="text-sm text-muted-foreground">Variables:</span>
            {prompt.template_variables.map(v => (
              <Badge key={v} variant="secondary" className="font-mono text-xs">
                {`{${v}}`}
              </Badge>
            ))}
          </div>
        )}
      </CardHeader>

      <Separator />

      <CardContent className="flex-1 overflow-hidden p-0">
        <ScrollArea className="h-full">
          <PromptContent content={prompt?.content || ""} />
        </ScrollArea>
      </CardContent>

      {/* Version selector if multiple versions exist */}
      {prompt?.all_versions && prompt.all_versions.length > 1 && (
        <>
          <Separator />
          <div className="p-4 flex items-center gap-2">
            <span className="text-sm text-muted-foreground">Versions:</span>
            {prompt.all_versions.map(v => (
              <Button
                key={v}
                variant={v === prompt.version ? "default" : "outline"}
                size="sm"
                className="h-7"
                onClick={() => onVersionChange(v)}
              >
                {v}
              </Button>
            ))}
          </div>
        </>
      )}
    </Card>
  );
}

// ============================================
// Main Page Component
// ============================================

export default function PromptsPage() {
  const [selectedPrompt, setSelectedPrompt] = React.useState<string | null>(null);
  const [selectedVersion, setSelectedVersion] = React.useState<string | undefined>(undefined);

  // Fetch prompt list
  const { data: promptList, isLoading: listLoading } = useQuery({
    queryKey: ["prompts"],
    queryFn: listPrompts,
  });

  // Fetch selected prompt detail
  const { data: promptDetail, isLoading: detailLoading } = useQuery({
    queryKey: ["prompt", selectedPrompt, selectedVersion],
    queryFn: () => getPrompt(selectedPrompt!, selectedVersion),
    enabled: !!selectedPrompt,
  });

  // Handle prompt selection
  const handleSelect = (name: string) => {
    setSelectedPrompt(name);
    setSelectedVersion(undefined); // Reset to default version
  };

  // Handle version change
  const handleVersionChange = (version: string) => {
    setSelectedVersion(version);
  };

  return (
    <div className="flex flex-col h-[calc(100vh-3.5rem)]">
      {/* Page header */}
      <div className="p-6 pb-4">
        <h1 className="text-3xl font-bold tracking-tight">Prompts</h1>
        <p className="text-muted-foreground">
          View and explore system prompt templates used by the RAG pipeline
        </p>
      </div>

      {/* Main content: master-detail layout */}
      <div className="flex flex-1 overflow-hidden px-6 pb-6 gap-6">
        {/* Left panel: Prompt list */}
        <PromptList
          prompts={promptList}
          isLoading={listLoading}
          selected={selectedPrompt}
          onSelect={handleSelect}
        />

        {/* Right panel: Prompt detail */}
        <PromptDetailPanel
          prompt={promptDetail}
          isLoading={detailLoading}
          hasSelection={!!selectedPrompt}
          onVersionChange={handleVersionChange}
        />
      </div>
    </div>
  );
}

"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import {
  Search,
  FileText,
  Filter,
  Loader2,
  ChevronDown,
  ExternalLink,
} from "lucide-react";

import { cn, formatNumber, truncate } from "@/lib/utils";
import { vectorSearch } from "@/lib/api";
import type { VectorRetrieveResponse, RetrievalResult } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Skeleton } from "@/components/ui/skeleton";

interface SearchResult extends RetrievalResult {
  preview?: string;
}

export default function SearchPage() {
  const router = useRouter();
  const [query, setQuery] = React.useState("");
  const [view, setView] = React.useState<"chunks" | "figures" | "tables">("chunks");
  const [topK, setTopK] = React.useState(10);
  const [isLoading, setIsLoading] = React.useState(false);
  const [results, setResults] = React.useState<SearchResult[]>([]);
  const [searchMeta, setSearchMeta] = React.useState<{
    query: string;
    total: number;
    view: string;
  } | null>(null);

  const [error, setError] = React.useState<string | null>(null);

  const handleResultClick = (result: SearchResult) => {
    const params = new URLSearchParams();
    params.set("doc_id", result.doc_id);
    params.set("node_id", result.chunk_id);
    router.push(`/inspect?${params.toString()}`);
  };

  const handleSearch = async (e?: React.FormEvent) => {
    e?.preventDefault();
    
    if (!query.trim()) return;
    
    setIsLoading(true);
    setError(null);
    try {
      const response = await vectorSearch({
        query: query.trim(),
        view,
        top_k: topK,
      });
      
      setResults(response.results);
      setSearchMeta({
        query: response.query,
        total: response.total,
        view: response.view,
      });
    } catch (err) {
      console.error("Search failed:", err);
      setError(err instanceof Error ? err.message : "Search failed. Please try again.");
      setSearchMeta(null);
      setResults([]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex flex-col gap-6 p-6">
      {/* Page header */}
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Search</h1>
        <p className="text-muted-foreground">
          Search your documents using semantic vector search
        </p>
      </div>

      {/* Search form */}
      <Card>
        <CardContent className="pt-6">
          <form onSubmit={handleSearch} className="space-y-4">
            <div className="flex gap-2">
              <div className="relative flex-1">
                <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Enter your search query..."
                  className="pl-10"
                />
              </div>
              <Button type="submit" disabled={isLoading || !query.trim()}>
                {isLoading ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  "Search"
                )}
              </Button>
            </div>

            <div className="flex items-center gap-4">
              <div className="flex items-center gap-2">
                <span className="text-sm text-muted-foreground">View:</span>
                <Select value={view} onValueChange={(v) => setView(v as typeof view)}>
                  <SelectTrigger className="w-[180px]">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="chunks">Text Chunks</SelectItem>
                    <SelectItem value="figures">Figures</SelectItem>
                    <SelectItem value="tables">Tables</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="flex items-center gap-2">
                <span className="text-sm text-muted-foreground">Results:</span>
                <Select value={String(topK)} onValueChange={(v) => setTopK(Number(v))}>
                  <SelectTrigger className="w-[80px]">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="5">5</SelectItem>
                    <SelectItem value="10">10</SelectItem>
                    <SelectItem value="20">20</SelectItem>
                    <SelectItem value="50">50</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
          </form>
        </CardContent>
      </Card>

      {/* Error display */}
      {error && (
        <Card className="border-destructive">
          <CardContent className="flex flex-col items-center justify-center py-8">
            <div className="text-destructive mb-2">Search Error</div>
            <p className="text-sm text-muted-foreground text-center max-w-md">
              {error}
            </p>
          </CardContent>
        </Card>
      )}

      {/* Results */}
      {isLoading ? (
        <div className="space-y-3">
          {[...Array(5)].map((_, i) => (
            <Skeleton key={i} className="h-24 w-full" />
          ))}
        </div>
      ) : searchMeta ? (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <p className="text-sm text-muted-foreground">
              Found {searchMeta.total} results for &ldquo;{searchMeta.query}&rdquo;
              <Badge variant="outline" className="ml-2">
                {searchMeta.view}
              </Badge>
            </p>
          </div>

          {results.length === 0 ? (
            <Card>
              <CardContent className="flex flex-col items-center justify-center py-12">
                <Search className="h-12 w-12 text-muted-foreground mb-4" />
                <p className="text-sm text-muted-foreground">
                  No results found for your query
                </p>
              </CardContent>
            </Card>
          ) : (
            <div className="space-y-3">
              {results.map((result, i) => (
                <Card 
                  key={`${result.chunk_id}-${i}`} 
                  className="hover:bg-accent/50 transition-colors cursor-pointer"
                  onClick={() => handleResultClick(result)}
                >
                  <CardContent className="p-4">
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex items-start gap-3 flex-1 min-w-0">
                        <div className="bg-muted p-2 rounded-md shrink-0">
                          <FileText className="h-4 w-4" />
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 mb-1 flex-wrap">
                            <p className="font-medium text-sm truncate max-w-[200px]" title={result.doc_id}>
                              {result.doc_id.slice(0, 12)}...
                            </p>
                            <Badge variant="secondary" className="text-xs shrink-0">
                              {(result.score * 100).toFixed(1)}% match
                            </Badge>
                            {result.page_no && (
                              <Badge variant="outline" className="text-xs shrink-0">
                                Page {result.page_no}
                              </Badge>
                            )}
                          </div>
                          {result.text_preview ? (
                            <p className="text-sm text-muted-foreground mt-2 line-clamp-3">
                              {result.text_preview}
                            </p>
                          ) : (
                            <p className="text-xs text-muted-foreground">
                              Chunk: {result.chunk_id.slice(0, 16)}...
                            </p>
                          )}
                        </div>
                      </div>
                      <div className="flex flex-col items-end gap-2 shrink-0">
                        <Badge variant="outline" className="text-xs">
                          #{i + 1}
                        </Badge>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-7 px-2 text-xs"
                          onClick={(e) => {
                            e.stopPropagation();
                            handleResultClick(result);
                          }}
                        >
                          <ExternalLink className="h-3 w-3 mr-1" />
                          View
                        </Button>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </div>
      ) : (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-12">
            <Search className="h-12 w-12 text-muted-foreground mb-4" />
            <h3 className="font-semibold">Enter a search query</h3>
            <p className="text-sm text-muted-foreground">
              Search across all your documents using semantic similarity
            </p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

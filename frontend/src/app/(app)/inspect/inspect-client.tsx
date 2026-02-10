"use client";

import * as React from "react";
import { useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import {
  Search,
  FileText,
  ImageIcon,
  Table2,
  Type,
  ArrowLeft,
  ArrowRight,
  Layers,
  AlertCircle,
  RefreshCw,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { listDocuments, listDocumentNodes } from "@/lib/api";
import type { Node } from "@/lib/api";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
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

// Node type icon
function NodeTypeIcon({ type }: { type: string }) {
  const icons: Record<string, React.ElementType> = {
    chunk: Type,
    figure: ImageIcon,
    table: Table2,
    page: FileText,
  };
  const Icon = icons[type] || FileText;
  return <Icon className="h-4 w-4" />;
}

// Node type badge
function NodeTypeBadge({ type }: { type: string }) {
  const colors: Record<string, string> = {
    chunk: "bg-blue-500/10 text-blue-500",
    figure: "bg-green-500/10 text-green-500",
    table: "bg-purple-500/10 text-purple-500",
    page: "bg-orange-500/10 text-orange-500",
  };
  
  return (
    <Badge variant="outline" className={cn("capitalize", colors[type])}>
      <NodeTypeIcon type={type} />
      <span className="ml-1">{type}</span>
    </Badge>
  );
}

// Node card in list
function NodeCard({
  node,
  isSelected,
  onClick,
}: {
  node: Node;
  isSelected: boolean;
  onClick: () => void;
}) {
  return (
    <Card
      className={cn(
        "cursor-pointer transition-colors",
        isSelected ? "ring-2 ring-primary" : "hover:bg-accent/50"
      )}
      onClick={onClick}
    >
      <CardContent className="p-3">
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-center gap-2">
            <NodeTypeBadge type={node.node_type} />
            {node.label && (
              <span className="text-sm font-medium">{node.label}</span>
            )}
          </div>
          {node.page_no && (
            <span className="text-xs text-muted-foreground">
              Page {node.page_no}
            </span>
          )}
        </div>
        <p className="text-xs text-muted-foreground mt-2 line-clamp-2">
          {node.text_plain || node.caption_md || "No preview available"}
        </p>
      </CardContent>
    </Card>
  );
}

// Node detail panel
function NodeDetail({ node }: { node: Node | null }) {
  if (!node) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center p-8">
        <Layers className="h-12 w-12 text-muted-foreground mb-4" />
        <h3 className="font-semibold">Select a node</h3>
        <p className="text-sm text-muted-foreground">
          Click on a node to view its details
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <div className="flex items-center gap-2 mb-2">
          <NodeTypeBadge type={node.node_type} />
          {node.label && (
            <span className="font-semibold">{node.label}</span>
          )}
        </div>
        <p className="text-xs text-muted-foreground font-mono">
          {node.node_id}
        </p>
      </div>

      {/* Location */}
      <div>
        <h4 className="text-sm font-semibold mb-2">Location</h4>
        <div className="grid grid-cols-2 gap-2 text-sm">
          <div className="flex justify-between">
            <span className="text-muted-foreground">Document</span>
            <span className="font-mono text-xs">{node.doc_id}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-muted-foreground">Version</span>
            <span>{node.version}</span>
          </div>
          {node.page_no && (
            <div className="flex justify-between">
              <span className="text-muted-foreground">Page</span>
              <span>{node.page_no}</span>
            </div>
          )}
          {node.chunk_index_in_page !== null && (
            <div className="flex justify-between">
              <span className="text-muted-foreground">Chunk Index</span>
              <span>{node.chunk_index_in_page}</span>
            </div>
          )}
        </div>
      </div>

      {/* Content */}
      <div>
        <h4 className="text-sm font-semibold mb-2">Content</h4>
        <Card className="bg-muted/50">
          <CardContent className="p-4">
            {node.caption_md && (
              <p className="text-sm italic mb-2">{node.caption_md}</p>
            )}
            <p className="text-sm whitespace-pre-wrap">
              {node.text_plain || node.text_md || "No text content"}
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Metadata */}
      {node.meta && Object.keys(node.meta).length > 0 && (
        <div>
          <h4 className="text-sm font-semibold mb-2">Metadata</h4>
          <Card className="bg-muted/50">
            <CardContent className="p-4">
              <pre className="text-xs overflow-auto">
                {JSON.stringify(node.meta, null, 2)}
              </pre>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Bounding Box */}
      {node.bbox && (
        <div>
          <h4 className="text-sm font-semibold mb-2">Bounding Box</h4>
          <div className="grid grid-cols-2 gap-2 text-xs">
            <div className="flex justify-between">
              <span className="text-muted-foreground">x0</span>
              <span>{node.bbox.x0}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">y0</span>
              <span>{node.bbox.y0}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">x1</span>
              <span>{node.bbox.x1}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">y1</span>
              <span>{node.bbox.y1}</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default function InspectClient() {
  const searchParams = useSearchParams();
  const [selectedDocId, setSelectedDocId] = React.useState<string | null>(null);
  const [selectedNode, setSelectedNode] = React.useState<Node | null>(null);
  const [typeFilter, setTypeFilter] = React.useState<string>("all");
  const [searchQuery, setSearchQuery] = React.useState("");
  const [page, setPage] = React.useState(1);
  const [pendingNodeId, setPendingNodeId] = React.useState<string | null>(null);

  // Handle URL parameters for deep linking
  React.useEffect(() => {
    const docIdParam = searchParams.get("doc_id");
    const nodeIdParam = searchParams.get("node_id");
    
    if (docIdParam && docIdParam !== selectedDocId) {
      setSelectedDocId(docIdParam);
      setSelectedNode(null);
      setPage(1);
      
      // Store pending node_id to select once nodes are loaded
      if (nodeIdParam) {
        setPendingNodeId(nodeIdParam);
      }
    }
  }, [searchParams, selectedDocId]);

  // Fetch documents for the selector
  const { data: docsData, isLoading: docsLoading } = useQuery({
    queryKey: ["documents-list"],
    queryFn: () => listDocuments({ limit: 100 }),
  });

  const documents = docsData?.items || [];

  // Fetch nodes for selected document
  const { data: nodesData, isLoading: nodesLoading, isError: nodesError, refetch: refetchNodes } = useQuery({
    queryKey: ["nodes", selectedDocId, typeFilter, page],
    queryFn: () => listDocumentNodes(selectedDocId!, {
      page,
      limit: 50,
      node_type: typeFilter !== "all" ? (typeFilter as "chunk" | "figure" | "table" | "page") : undefined,
    }),
    enabled: !!selectedDocId,
  });

  const nodes = nodesData?.items || [];
  const totalNodes = nodesData?.total || 0;
  const hasMore = nodesData?.has_more || false;

  // Auto-select node from URL parameter once nodes are loaded
  React.useEffect(() => {
    if (pendingNodeId && nodes.length > 0 && !nodesLoading) {
      const targetNode = nodes.find(n => n.node_id === pendingNodeId);
      if (targetNode) {
        setSelectedNode(targetNode);
        setPendingNodeId(null);
      }
    }
  }, [pendingNodeId, nodes, nodesLoading]);

  // Filter nodes by search
  const filteredNodes = React.useMemo(() => {
    if (!searchQuery) return nodes;
    const query = searchQuery.toLowerCase();
    return nodes.filter((node) =>
      node.node_id.toLowerCase().includes(query) ||
      node.text_plain?.toLowerCase().includes(query) ||
      node.label?.toLowerCase().includes(query)
    );
  }, [nodes, searchQuery]);

  return (
    <div className="flex flex-col h-[calc(100vh-3.5rem)]">
      {/* Page header */}
      <div className="p-6 pb-4">
        <h1 className="text-3xl font-bold tracking-tight">Inspect</h1>
        <p className="text-muted-foreground">
          Browse and inspect document chunks and nodes
        </p>
      </div>

      {/* Document selector */}
      <div className="px-6 pb-4">
        <Select value={selectedDocId || ""} onValueChange={(v) => { setSelectedDocId(v); setSelectedNode(null); setPage(1); }}>
          <SelectTrigger className="w-full max-w-md">
            <SelectValue placeholder="Select a document to inspect..." />
          </SelectTrigger>
          <SelectContent>
            {docsLoading ? (
              <SelectItem value="__loading__" disabled>Loading documents...</SelectItem>
            ) : documents.length === 0 ? (
              <SelectItem value="__empty__" disabled>No documents found</SelectItem>
            ) : (
              documents.map((doc) => (
                <SelectItem key={doc.doc_id} value={doc.doc_id}>
                  {doc.source_uri.split("/").pop() || doc.doc_id}
                </SelectItem>
              ))
            )}
          </SelectContent>
        </Select>
      </div>

      {/* Content */}
      {!selectedDocId ? (
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center">
            <Layers className="h-16 w-16 text-muted-foreground mx-auto mb-4" />
            <h3 className="font-semibold text-lg">Select a document</h3>
            <p className="text-sm text-muted-foreground">
              Choose a document above to browse its nodes
            </p>
          </div>
        </div>
      ) : (
        <div className="flex-1 flex gap-4 px-6 pb-6 overflow-hidden">
          {/* Node list */}
          <div className="w-1/2 flex flex-col gap-4">
            {/* Filters */}
            <div className="flex items-center gap-2">
              <div className="relative flex-1">
                <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Search nodes..."
                  className="pl-10"
                />
              </div>
              <Select value={typeFilter} onValueChange={(v) => { setTypeFilter(v); setPage(1); }}>
                <SelectTrigger className="w-[130px]">
                  <SelectValue placeholder="Type" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Types</SelectItem>
                  <SelectItem value="chunk">Chunks</SelectItem>
                  <SelectItem value="figure">Figures</SelectItem>
                  <SelectItem value="table">Tables</SelectItem>
                </SelectContent>
              </Select>
              <Button variant="outline" size="icon" onClick={() => refetchNodes()}>
                <RefreshCw className="h-4 w-4" />
              </Button>
            </div>

            {/* Node list */}
            <Card className="flex-1 overflow-hidden">
              <CardHeader className="pb-2">
                <CardTitle className="text-base">Nodes</CardTitle>
                <CardDescription>
                  {totalNodes} node{totalNodes !== 1 ? "s" : ""} found
                </CardDescription>
              </CardHeader>
              <CardContent className="p-0">
                <ScrollArea className="h-[calc(100vh-26rem)]">
                  <div className="space-y-2 p-4">
                    {nodesLoading ? (
                      <div className="space-y-2">
                        {[...Array(5)].map((_, i) => (
                          <Skeleton key={i} className="h-20 w-full" />
                        ))}
                      </div>
                    ) : nodesError ? (
                      <div className="text-center py-8 text-destructive">
                        <AlertCircle className="h-8 w-8 mx-auto mb-2" />
                        <p className="text-sm">Failed to load nodes</p>
                        <Button variant="outline" size="sm" onClick={() => refetchNodes()} className="mt-2">
                          Try Again
                        </Button>
                      </div>
                    ) : filteredNodes.length === 0 ? (
                      <div className="text-center py-8 text-muted-foreground">
                        <Layers className="h-8 w-8 mx-auto mb-2" />
                        <p className="text-sm">No nodes found</p>
                      </div>
                    ) : (
                      filteredNodes.map((node) => (
                        <NodeCard
                          key={node.node_id}
                          node={node}
                          isSelected={selectedNode?.node_id === node.node_id}
                          onClick={() => setSelectedNode(node)}
                        />
                      ))
                    )}
                  </div>
                </ScrollArea>
                
                {/* Pagination */}
                {totalNodes > 50 && (
                  <div className="flex items-center justify-between p-4 border-t">
                    <p className="text-xs text-muted-foreground">
                      Page {page}
                    </p>
                    <div className="flex gap-2">
                      <Button
                        variant="outline"
                        size="sm"
                        disabled={page === 1}
                        onClick={() => setPage(page - 1)}
                      >
                        <ArrowLeft className="h-4 w-4" />
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        disabled={!hasMore}
                        onClick={() => setPage(page + 1)}
                      >
                        <ArrowRight className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>

          {/* Detail panel */}
          <Card className="w-1/2 overflow-hidden">
            <CardHeader className="pb-2">
              <CardTitle className="text-base">Node Details</CardTitle>
            </CardHeader>
            <CardContent>
              <ScrollArea className="h-[calc(100vh-22rem)]">
                <NodeDetail node={selectedNode} />
              </ScrollArea>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}

"use client";

import * as React from "react";
import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import {
  FileText,
  Upload,
  Search,
  Filter,
  MoreHorizontal,
  Eye,
  MessageSquare,
  RefreshCw,
  Trash2,
  ChevronDown,
  AlertCircle,
  Shield,
  Info,
} from "lucide-react";

import { cn, formatDate, formatRelativeTime, getFilename } from "@/lib/utils";
import { listDocuments, getHealth } from "@/lib/api";
import type { DocumentGraph } from "@/lib/api";
import { PermissionsBadge } from "@/components/documents/permissions-badge";
import { PermissionsDialog } from "@/components/documents/permissions-dialog";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Skeleton } from "@/components/ui/skeleton";
import { UploadDialog } from "@/components/documents/upload-dialog";

function StatusBadge({ embedded }: { embedded: boolean }) {
  if (embedded) {
    return <Badge variant="default">Indexed</Badge>;
  }
  return <Badge variant="secondary">Processing</Badge>;
}

function AuthorityBadge({ tier }: { tier: number }) {
  const labels: Record<number, string> = {
    1: "Tier 1",
    2: "Tier 2",
    3: "Tier 3",
  };
  return (
    <Badge variant="outline" className="text-xs">
      {labels[tier] || `Tier ${tier}`}
    </Badge>
  );
}

function DocumentsContent() {
  const searchParams = useSearchParams();

  // Skip SSR for Radix components — avoids hydration ID mismatch
  const [mounted, setMounted] = React.useState(false);
  React.useEffect(() => setMounted(true), []);

  const [uploadOpen, setUploadOpen] = React.useState(
    searchParams.get("upload") === "true"
  );
  const [searchQuery, setSearchQuery] = React.useState("");
  const [page, setPage] = React.useState(1);
  const [docTypeFilter, setDocTypeFilter] = React.useState<string | null>(null);
  const [aclEnabled, setAclEnabled] = React.useState(false);
  const [supportedTypes, setSupportedTypes] = React.useState<string[] | null>(null);
  const [permissionsDocId, setPermissionsDocId] = React.useState<string | null>(null);

  React.useEffect(() => {
    getHealth()
      .then((h) => {
        setAclEnabled(!!h.features?.acl_enabled);
        if (h.features?.supported_file_types?.length) {
          setSupportedTypes(h.features.supported_file_types);
        }
      })
      .catch(() => {});
  }, []);

  const pdfOnly = supportedTypes !== null && supportedTypes.length === 1 && supportedTypes[0] === "pdf";

  // Fetch documents from API
  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["documents", page, searchQuery, docTypeFilter],
    queryFn: () => listDocuments({
      page,
      limit: 20,
      search: searchQuery || undefined,
      doc_type: docTypeFilter || undefined,
    }),
    staleTime: 30000,
  });

  const documents = data?.items || [];
  const totalDocuments = data?.total || 0;
  const hasMore = data?.has_more || false;

  if (!mounted) return <DocumentsLoading />;

  return (
    <div className="flex flex-col gap-6 p-6">
      {/* Page header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Documents</h1>
          <p className="text-muted-foreground">
            Manage and browse your ingested documents
          </p>
        </div>
        <Button onClick={() => setUploadOpen(true)}>
          <Upload className="mr-2 h-4 w-4" />
          Upload Document
        </Button>
      </div>

      {/* Search and filters */}
      <div className="flex items-center gap-4">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder="Search documents..."
            value={searchQuery}
            onChange={(e) => {
              setSearchQuery(e.target.value);
              setPage(1);
            }}
            className="pl-9"
          />
        </div>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="outline" size="sm">
              <Filter className="mr-2 h-4 w-4" />
              {docTypeFilter || "Filter"}
              <ChevronDown className="ml-2 h-4 w-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-48">
            <DropdownMenuItem onClick={() => { setDocTypeFilter(null); setPage(1); }}>
              All Documents
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={() => { setDocTypeFilter("policy"); setPage(1); }}>
              Policy
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => { setDocTypeFilter("spec"); setPage(1); }}>
              Spec
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => { setDocTypeFilter("contract"); setPage(1); }}>
              Contract
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => { setDocTypeFilter("memo"); setPage(1); }}>
              Memo
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
        <Button variant="outline" size="sm" onClick={() => refetch()}>
          <RefreshCw className="h-4 w-4" />
        </Button>
      </div>

      {/* File type notice */}
      {pdfOnly && (
        <Alert>
          <Info className="h-4 w-4" />
          <AlertDescription>
            Only <strong>PDF</strong> files are currently supported. Enable the Docling backend to process DOCX, PPTX, XLSX, HTML, Markdown, and CSV files.
          </AlertDescription>
        </Alert>
      )}

      {/* Documents table */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">All Documents</CardTitle>
          <CardDescription>
            {totalDocuments} document{totalDocuments !== 1 ? "s" : ""} found
          </CardDescription>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="space-y-3">
              {[...Array(5)].map((_, i) => (
                <Skeleton key={i} className="h-12 w-full" />
              ))}
            </div>
          ) : isError ? (
            <div className="flex flex-col items-center justify-center py-12 text-center">
              <AlertCircle className="h-12 w-12 text-destructive mb-4" />
              <h3 className="font-semibold">Failed to load documents</h3>
              <p className="text-sm text-muted-foreground mb-4">
                {error instanceof Error ? error.message : "Unknown error"}
              </p>
              <Button onClick={() => refetch()}>Try Again</Button>
            </div>
          ) : documents.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-center">
              <FileText className="h-12 w-12 text-muted-foreground mb-4" />
              <h3 className="font-semibold">No documents found</h3>
              <p className="text-sm text-muted-foreground mb-4">
                {searchQuery || docTypeFilter
                  ? "Try adjusting your search or filters"
                  : "Upload your first document to get started"}
              </p>
              {!searchQuery && !docTypeFilter && (
                <Button onClick={() => setUploadOpen(true)}>
                  <Upload className="mr-2 h-4 w-4" />
                  Upload Document
                </Button>
              )}
            </div>
          ) : (
            <>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Document</TableHead>
                    <TableHead>Type</TableHead>
                    <TableHead>Department</TableHead>
                    <TableHead>Authority</TableHead>
                    {aclEnabled && <TableHead>Visibility</TableHead>}
                    <TableHead>Ingested</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead className="w-[50px]"></TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {documents.map((doc) => (
                    <TableRow key={doc.doc_id}>
                      <TableCell>
                        <div className="flex items-center gap-3">
                          <div className="bg-muted p-2 rounded-md">
                            <FileText className="h-4 w-4" />
                          </div>
                          <div>
                            <p className="font-medium">
                              {getFilename(doc.source_uri)}
                            </p>
                            <p className="text-xs text-muted-foreground">
                              {doc.doc_id}
                            </p>
                          </div>
                        </div>
                      </TableCell>
                      <TableCell>
                        <Badge variant="secondary" className="capitalize">
                          {doc.doc_type || "—"}
                        </Badge>
                      </TableCell>
                      <TableCell className="capitalize">
                        {doc.department || "—"}
                      </TableCell>
                      <TableCell>
                        {doc.authority_tier ? (
                          <AuthorityBadge tier={doc.authority_tier} />
                        ) : (
                          "—"
                        )}
                      </TableCell>
                      {aclEnabled && (
                        <TableCell>
                          <PermissionsBadge visibility={doc.visibility} />
                        </TableCell>
                      )}
                      <TableCell>
                        <span title={formatDate(doc.ingested_at)}>
                          {formatRelativeTime(doc.ingested_at)}
                        </span>
                      </TableCell>
                      <TableCell>
                        <StatusBadge embedded={!!doc.embedded_collection_version} />
                      </TableCell>
                      <TableCell>
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button variant="ghost" size="icon" className="h-8 w-8">
                              <MoreHorizontal className="h-4 w-4" />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end">
                            <DropdownMenuItem>
                              <Eye className="mr-2 h-4 w-4" />
                              View Details
                            </DropdownMenuItem>
                            <DropdownMenuItem>
                              <MessageSquare className="mr-2 h-4 w-4" />
                              Chat with Document
                            </DropdownMenuItem>
                            {aclEnabled && (
                              <DropdownMenuItem onClick={() => setPermissionsDocId(doc.doc_id)}>
                                <Shield className="mr-2 h-4 w-4" />
                                Permissions
                              </DropdownMenuItem>
                            )}
                            <DropdownMenuItem>
                              <RefreshCw className="mr-2 h-4 w-4" />
                              Re-index
                            </DropdownMenuItem>
                            <DropdownMenuSeparator />
                            <DropdownMenuItem className="text-destructive">
                              <Trash2 className="mr-2 h-4 w-4" />
                              Delete
                            </DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>

              {/* Pagination */}
              <div className="flex items-center justify-between mt-4">
                <p className="text-sm text-muted-foreground">
                  Page {page} of {Math.ceil(totalDocuments / 20)}
                </p>
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={page === 1}
                    onClick={() => setPage(page - 1)}
                  >
                    Previous
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={!hasMore}
                    onClick={() => setPage(page + 1)}
                  >
                    Next
                  </Button>
                </div>
              </div>
            </>
          )}
        </CardContent>
      </Card>

      {/* Upload dialog */}
      <UploadDialog open={uploadOpen} onOpenChange={setUploadOpen} supportedTypes={supportedTypes} aclEnabled={aclEnabled} />

      {/* Permissions dialog */}
      <PermissionsDialog
        docId={permissionsDocId}
        open={!!permissionsDocId}
        onOpenChange={(open) => { if (!open) setPermissionsDocId(null); }}
      />
    </div>
  );
}

function DocumentsLoading() {
  return (
    <div className="flex flex-col gap-6 p-6">
      <div className="flex items-center justify-between">
        <div>
          <Skeleton className="h-9 w-48 mb-2" />
          <Skeleton className="h-5 w-64" />
        </div>
        <Skeleton className="h-10 w-40" />
      </div>
      <div className="space-y-3">
        {[...Array(5)].map((_, i) => (
          <Skeleton key={i} className="h-12 w-full" />
        ))}
      </div>
    </div>
  );
}

export default function DocumentsPage() {
  return (
    <Suspense fallback={<DocumentsLoading />}>
      <DocumentsContent />
    </Suspense>
  );
}

"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { Upload, X, FileText, CheckCircle, AlertCircle, Info, Loader2, ChevronDown, Clock } from "lucide-react";
import { toast } from "sonner";

import { cn, formatFileSize } from "@/lib/utils";
import { ingestDocument, pollIngestJob, embedDocument, pollEmbedJob, getHealth, APIError } from "@/lib/api";
import type { Visibility, IngestJob, EmbeddingJob } from "@/lib/api";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { TagInput } from "@/components/ui/tag-input";

interface UploadDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Backend-supported file types (e.g. ["pdf"]). Null = still loading, uses all types as fallback. */
  supportedTypes?: string[] | null;
  aclEnabled?: boolean;
}

type UploadStage = "idle" | "uploading" | "ingesting" | "embedding" | "complete" | "duplicate" | "error";

interface DuplicateInfo {
  doc_id: string;
  source_uri?: string;
  ingested_at?: string;
  node_count?: number;
  doc_type?: string;
  content_hash?: string;
}

// Map backend source_type → file extensions + MIME types
const TYPE_CONFIG: Record<string, { extensions: string[]; mimeTypes: string[]; label: string }> = {
  pdf:  { extensions: [".pdf"],  mimeTypes: ["application/pdf"], label: "PDF" },
  docx: { extensions: [".docx"], mimeTypes: ["application/vnd.openxmlformats-officedocument.wordprocessingml.document"], label: "DOCX" },
  pptx: { extensions: [".pptx"], mimeTypes: ["application/vnd.openxmlformats-officedocument.presentationml.presentation"], label: "PPTX" },
  xlsx: { extensions: [".xlsx"], mimeTypes: ["application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"], label: "XLSX" },
  html: { extensions: [".html", ".htm"], mimeTypes: ["text/html"], label: "HTML" },
  md:   { extensions: [".md", ".markdown"], mimeTypes: ["text/markdown"], label: "Markdown" },
  csv:  { extensions: [".csv"], mimeTypes: ["text/csv"], label: "CSV" },
  txt:  { extensions: [".txt"], mimeTypes: ["text/plain"], label: "TXT" },
};

// All known types (fallback when health hasn't responded yet)
const ALL_SOURCE_TYPES = Object.keys(TYPE_CONFIG);

// Map backend pipeline_stage values to user-friendly messages
const INGEST_STAGE_LABELS: Record<string, string> = {
  retrieving_file: "Retrieving file from storage...",
  resolving_backend: "Selecting processing engine...",
  extracting_content: "Extracting text and figures...",
  chunking: "Splitting into chunks...",
  creating_nodes: "Building document graph...",
  persisting: "Saving to database...",
};

const EMBED_STAGE_LABELS: Record<string, string> = {
  loading_nodes: "Loading document nodes...",
  generating_embeddings: "Generating vector embeddings...",
  indexing_vectors: "Indexing vectors for search...",
  complete: "Embedding complete",
};

function formatElapsed(ms: number): string {
  const secs = Math.floor(ms / 1000);
  if (secs < 60) return `${secs}s`;
  const mins = Math.floor(secs / 60);
  const remSecs = secs % 60;
  return `${mins}m ${remSecs}s`;
}

export function UploadDialog({ open, onOpenChange, supportedTypes: supportedTypesProp, aclEnabled: aclEnabledProp }: UploadDialogProps) {
  const router = useRouter();
  const [isDragging, setIsDragging] = React.useState(false);
  const [file, setFile] = React.useState<File | null>(null);
  const [stage, setStage] = React.useState<UploadStage>("idle");
  const [progress, setProgress] = React.useState(0);
  const [error, setError] = React.useState<string | null>(null);
  const [docId, setDocId] = React.useState<string | null>(null);
  const [duplicateInfo, setDuplicateInfo] = React.useState<DuplicateInfo | null>(null);
  const [statusMessage, setStatusMessage] = React.useState<string>("");
  const [startTime, setStartTime] = React.useState<number | null>(null);
  const [elapsed, setElapsed] = React.useState(0);
  const fileInputRef = React.useRef<HTMLInputElement>(null);

  // ACL state — prefer prop from parent, fall back to own fetch
  const [aclEnabledLocal, setAclEnabledLocal] = React.useState(false);
  const [supportedTypesLocal, setSupportedTypesLocal] = React.useState<string[] | null>(null);
  const [aclExpanded, setAclExpanded] = React.useState(false);
  const [visibility, setVisibility] = React.useState<Visibility>("public");
  const [allowedRoles, setAllowedRoles] = React.useState<string[]>([]);
  const [allowedGroups, setAllowedGroups] = React.useState<string[]>([]);
  const [allowedUsers, setAllowedUsers] = React.useState<string[]>([]);

  // Only fetch health if parent didn't provide props
  React.useEffect(() => {
    if (aclEnabledProp !== undefined && supportedTypesProp !== undefined) return;
    getHealth()
      .then((h) => {
        if (aclEnabledProp === undefined) setAclEnabledLocal(!!h.features?.acl_enabled);
        if (supportedTypesProp === undefined && h.features?.supported_file_types?.length) {
          setSupportedTypesLocal(h.features.supported_file_types);
        }
      })
      .catch(() => {});
  }, [aclEnabledProp, supportedTypesProp]);

  const aclEnabled = aclEnabledProp ?? aclEnabledLocal;

  // Derive allowed extensions and MIME types from supported types
  const activeTypes = (supportedTypesProp ?? supportedTypesLocal) ?? ALL_SOURCE_TYPES;
  const allowedExtensions = React.useMemo(
    () => activeTypes.flatMap((t) => TYPE_CONFIG[t]?.extensions ?? []),
    [activeTypes],
  );
  const allowedMimeTypes = React.useMemo(
    () => activeTypes.flatMap((t) => TYPE_CONFIG[t]?.mimeTypes ?? []),
    [activeTypes],
  );
  const typeHelpText = React.useMemo(
    () => activeTypes.map((t) => TYPE_CONFIG[t]?.label ?? t.toUpperCase()).join(", "),
    [activeTypes],
  );

  // Elapsed time ticker
  React.useEffect(() => {
    if (!startTime || stage === "idle" || stage === "complete" || stage === "error" || stage === "duplicate") {
      return;
    }
    const timer = setInterval(() => {
      setElapsed(Date.now() - startTime);
    }, 1000);
    return () => clearInterval(timer);
  }, [startTime, stage]);

  const reset = React.useCallback(() => {
    setFile(null);
    setStage("idle");
    setProgress(0);
    setError(null);
    setDocId(null);
    setDuplicateInfo(null);
    setStatusMessage("");
    setStartTime(null);
    setElapsed(0);
    setAclExpanded(false);
    setVisibility("public");
    setAllowedRoles([]);
    setAllowedGroups([]);
    setAllowedUsers([]);
  }, []);

  const handleOpenChange = React.useCallback((nextOpen: boolean) => {
    const busy = stage === "uploading" || stage === "ingesting" || stage === "embedding";
    // Prevent closing while jobs are in-flight to avoid inconsistent state.
    if (!nextOpen && busy) return;
    if (!nextOpen) reset();
    onOpenChange(nextOpen);
  }, [stage, reset, onOpenChange]);

  const handleClose = React.useCallback(() => {
    handleOpenChange(false);
  }, [handleOpenChange]);

  const extractFilename = (sourceUri?: string) => {
    if (!sourceUri) return null;
    return sourceUri.replace(/^upload:\/\//, "");
  };

  const validateFile = (file: File): string | null => {
    // Check file type
    const extension = "." + file.name.split(".").pop()?.toLowerCase();
    if (!allowedExtensions.includes(extension) && !allowedMimeTypes.includes(file.type)) {
      return `Unsupported file type. Allowed: ${typeHelpText}`;
    }

    // Check file size (50MB max)
    if (file.size > 50 * 1024 * 1024) {
      return "File size exceeds 50MB limit";
    }

    return null;
  };

  const handleFileSelect = (selectedFile: File) => {
    const validationError = validateFile(selectedFile);
    if (validationError) {
      setError(validationError);
      return;
    }
    setError(null);
    setFile(selectedFile);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);

    const droppedFile = e.dataTransfer.files[0];
    if (droppedFile) {
      handleFileSelect(droppedFile);
    }
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = e.target.files?.[0];
    if (selectedFile) {
      handleFileSelect(selectedFile);
    }
  };

  const handleUpload = async () => {
    if (!file) return;

    setStartTime(Date.now());
    setElapsed(0);

    try {
      // Stage 1: Upload and ingest
      setStage("uploading");
      setProgress(5);
      setStatusMessage("Uploading file to server...");

      const aclOptions = aclEnabled && visibility !== "public" ? {
        visibility,
        allowed_roles: visibility === "internal" ? allowedRoles : undefined,
        allowed_groups: visibility === "internal" ? allowedGroups : undefined,
        allowed_users: visibility === "restricted" ? allowedUsers : undefined,
      } : aclEnabled ? { visibility } : undefined;

      let ingestResponse;
      try {
        ingestResponse = await ingestDocument(file, aclOptions);
      } catch (e) {
        // Handle duplicate detection (409)
        if (e instanceof APIError && e.status === 409 && typeof e.detail === "object" && e.detail !== null) {
          const body = e.detail as { detail?: string; existing_document?: DuplicateInfo };
          if (body.detail === "duplicate" && body.existing_document) {
            setDuplicateInfo(body.existing_document);
            setStage("duplicate");
            return;
          }
        }
        // Handle unsupported file type (415)
        if (e instanceof APIError && e.status === 415) {
          const detail = typeof e.detail === "object" && e.detail !== null ? (e.detail as { detail?: string }).detail : String(e.detail);
          throw new Error(detail || "Unsupported file type");
        }
        // Handle server errors with clear message
        if (e instanceof APIError) {
          throw new Error(`Upload failed (HTTP ${e.status}): ${typeof e.detail === "object" ? JSON.stringify(e.detail) : e.detail || e.message}`);
        }
        throw e;
      }

      setDocId(ingestResponse.doc_id);
      setProgress(15);

      // Stage 2: Poll ingestion
      setStage("ingesting");
      setStatusMessage("Queued for processing...");

      let ingestResult;
      try {
        ingestResult = await pollIngestJob(ingestResponse.job_id, {
          interval: 2000,
          maxAttempts: 150, // 5 minutes
          onProgress: (job: IngestJob) => {
            // Show the backend's granular stage message
            if (job.pipeline_stage && INGEST_STAGE_LABELS[job.pipeline_stage]) {
              setStatusMessage(INGEST_STAGE_LABELS[job.pipeline_stage]);
            } else if (job.status === "pending") {
              setStatusMessage("Queued, waiting for worker...");
            } else if (job.status === "processing") {
              setStatusMessage("Processing document...");
            }

            // FIX: Use functional updater to avoid stale closure
            if (job.status === "processing") {
              setProgress(prev => Math.min(48, prev + 3));
            } else if (job.status === "pending") {
              // Show slow movement even during queue wait
              setProgress(prev => Math.min(20, prev + 1));
            }
          },
        });
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e);
        if (msg.includes("timeout")) {
          throw new Error("Ingestion timed out after 5 minutes. The worker may be overloaded or not running. Check the Processing page for job status.");
        }
        throw new Error(`Ingestion failed: ${msg}`);
      }
      setProgress(50);

      // Stage 3: Trigger embedding
      setStage("embedding");
      setStatusMessage("Starting embedding generation...");

      let embedResponse;
      try {
        embedResponse = await embedDocument({
          doc_id: ingestResponse.doc_id,
          version_id: ingestResponse.version_id,
        });
      } catch (e) {
        if (e instanceof APIError && e.status === 404) {
          throw new Error("Document nodes not found for embedding. Ingestion may have created an alias for duplicate content.");
        }
        throw new Error(`Failed to start embedding: ${e instanceof Error ? e.message : String(e)}`);
      }
      setProgress(55);

      // Stage 4: Poll embedding
      try {
        await pollEmbedJob(embedResponse.job_id, {
          interval: 3000,
          maxAttempts: 150, // ~7.5 minutes
          onProgress: (job: EmbeddingJob) => {
            // Show the backend's granular stage message
            if (job.pipeline_stage && EMBED_STAGE_LABELS[job.pipeline_stage]) {
              setStatusMessage(EMBED_STAGE_LABELS[job.pipeline_stage]);
            } else if (job.status === "pending") {
              setStatusMessage("Queued for embedding...");
            } else if (job.status === "processing") {
              setStatusMessage("Generating embeddings...");
            }

            // FIX: Use functional updater to avoid stale closure
            if (job.status === "processing" && job.chunk_count) {
              const embedPct = Math.min(95, 55 + ((job.record_count || 0) / job.chunk_count) * 40);
              setProgress(embedPct);
            } else if (job.status === "processing") {
              setProgress(prev => Math.min(75, prev + 2));
            } else if (job.status === "pending") {
              setProgress(prev => Math.min(58, prev + 1));
            }
          },
        });
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e);
        if (msg.includes("timeout")) {
          throw new Error("Embedding timed out after 7 minutes. The document may be very large. Check the Processing page for job status.");
        }
        throw new Error(`Embedding failed: ${msg}`);
      }
      setProgress(100);

      // Complete
      setStage("complete");
      setStatusMessage("Done!");
      toast.success("Document uploaded and indexed successfully!");

    } catch (e) {
      setStage("error");
      const errorMessage = e instanceof Error ? e.message : "Upload failed";
      setError(errorMessage);
      toast.error(errorMessage);
    }
  };

  const getStageLabel = (): string => {
    if (statusMessage) return statusMessage;
    const defaults: Record<UploadStage, string> = {
      idle: "Ready to upload",
      uploading: "Uploading document...",
      ingesting: "Processing document...",
      embedding: "Generating embeddings...",
      complete: "Complete!",
      duplicate: "Already processed",
      error: "Error",
    };
    return defaults[stage];
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Upload Document</DialogTitle>
          <DialogDescription>
            Upload a document to process and add to your knowledge base.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {/* Drop zone */}
          {stage === "idle" && !file && (
            <div
              className={cn(
                "border-2 border-dashed rounded-lg p-8 text-center transition-colors cursor-pointer",
                isDragging
                  ? "border-primary bg-primary/5"
                  : "border-muted-foreground/25 hover:border-primary/50"
              )}
              onDrop={handleDrop}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onClick={() => fileInputRef.current?.click()}
            >
              <input
                ref={fileInputRef}
                type="file"
                className="hidden"
                accept={allowedExtensions.join(",")}
                onChange={handleInputChange}
              />
              <Upload className="h-10 w-10 mx-auto mb-4 text-muted-foreground" />
              <p className="text-sm font-medium">
                Drop your file here or click to browse
              </p>
              <p className="text-xs text-muted-foreground mt-1">
                {typeHelpText} (max 50MB)
              </p>
            </div>
          )}

          {/* Selected file */}
          {file && stage === "idle" && (
            <div className="flex items-center gap-3 p-3 rounded-lg bg-muted">
              <div className="bg-background p-2 rounded-md">
                <FileText className="h-5 w-5" />
              </div>
              <div className="flex-1 min-w-0">
                <p className="font-medium truncate">{file.name}</p>
                <p className="text-xs text-muted-foreground">
                  {formatFileSize(file.size)}
                </p>
              </div>
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8"
                onClick={() => setFile(null)}
              >
                <X className="h-4 w-4" />
              </Button>
            </div>
          )}

          {/* Access Control (visible when ACL enabled + file selected + idle) */}
          {aclEnabled && stage === "idle" && file && (
            <Collapsible open={aclExpanded} onOpenChange={setAclExpanded}>
              <CollapsibleTrigger asChild>
                <button
                  type="button"
                  className="flex w-full items-center justify-between rounded-md border px-3 py-2 text-sm hover:bg-muted transition-colors"
                >
                  <span className="font-medium">Access Control</span>
                  <ChevronDown className={cn("h-4 w-4 transition-transform", aclExpanded && "rotate-180")} />
                </button>
              </CollapsibleTrigger>
              <CollapsibleContent className="space-y-3 pt-3">
                <div className="space-y-1.5">
                  <p className="text-sm font-medium">Visibility</p>
                  <Select value={visibility} onValueChange={(v) => setVisibility(v as Visibility)}>
                    <SelectTrigger className="w-full">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="public">Public</SelectItem>
                      <SelectItem value="internal">Internal</SelectItem>
                      <SelectItem value="restricted">Restricted</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                {visibility === "internal" && (
                  <>
                    <div className="space-y-1.5">
                      <p className="text-sm font-medium">Allowed Roles</p>
                      <TagInput value={allowedRoles} onChange={setAllowedRoles} placeholder="Add role..." />
                    </div>
                    <div className="space-y-1.5">
                      <p className="text-sm font-medium">Allowed Groups</p>
                      <TagInput value={allowedGroups} onChange={setAllowedGroups} placeholder="Add group..." />
                    </div>
                  </>
                )}
                {visibility === "restricted" && (
                  <div className="space-y-1.5">
                    <p className="text-sm font-medium">Allowed Users</p>
                    <TagInput value={allowedUsers} onChange={setAllowedUsers} placeholder="Add user ID..." />
                  </div>
                )}
              </CollapsibleContent>
            </Collapsible>
          )}

          {/* Progress */}
          {(stage === "uploading" || stage === "ingesting" || stage === "embedding") && (
            <div className="space-y-3">
              <div className="flex items-center gap-3">
                <Loader2 className="h-5 w-5 animate-spin text-primary" />
                <span className="text-sm font-medium flex-1">{getStageLabel()}</span>
                {startTime && elapsed > 0 && (
                  <span className="text-xs text-muted-foreground flex items-center gap-1">
                    <Clock className="h-3 w-3" />
                    {formatElapsed(elapsed)}
                  </span>
                )}
              </div>
              <Progress value={progress} className="h-2" />
              <p className="text-xs text-muted-foreground text-center">
                {Math.round(progress)}% complete
              </p>
            </div>
          )}

          {/* Complete */}
          {stage === "complete" && (
            <div className="flex flex-col items-center gap-3 py-4">
              <div className="bg-green-500/10 p-3 rounded-full">
                <CheckCircle className="h-8 w-8 text-green-500" />
              </div>
              <div className="text-center">
                <p className="font-medium">Document indexed successfully!</p>
                <p className="text-sm text-muted-foreground">
                  {file?.name}
                </p>
                {startTime && (
                  <p className="text-xs text-muted-foreground mt-1">
                    Completed in {formatElapsed(elapsed)}
                  </p>
                )}
              </div>
            </div>
          )}

          {/* Duplicate */}
          {stage === "duplicate" && duplicateInfo && (
            <div className="flex flex-col items-center gap-3 py-4">
              <div className="bg-blue-500/10 p-3 rounded-full">
                <Info className="h-8 w-8 text-blue-500" />
              </div>
              <div className="text-center">
                <p className="font-medium">This document has already been processed</p>
                <p className="text-sm text-muted-foreground mt-1">
                  {extractFilename(duplicateInfo.source_uri) || file?.name}
                </p>
              </div>
              <div className="w-full rounded-lg border p-3 text-sm space-y-1">
                {duplicateInfo.doc_type && (
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Type</span>
                    <span className="font-medium capitalize">{duplicateInfo.doc_type}</span>
                  </div>
                )}
                {duplicateInfo.ingested_at && (
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Ingested</span>
                    <span className="font-medium">
                      {new Date(duplicateInfo.ingested_at).toLocaleDateString()}
                    </span>
                  </div>
                )}
                {duplicateInfo.node_count != null && (
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Nodes</span>
                    <span className="font-medium">{duplicateInfo.node_count}</span>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Error */}
          {error && stage !== "complete" && (
            <div className="flex items-start gap-2 p-3 rounded-lg bg-destructive/10 text-destructive">
              <AlertCircle className="h-5 w-5 shrink-0 mt-0.5" />
              <div className="text-sm space-y-1">
                <p className="font-medium">Processing failed</p>
                <p className="text-xs opacity-90">{error}</p>
              </div>
            </div>
          )}

          {/* Actions */}
          <div className="flex justify-end gap-2">
            {stage === "idle" && (
              <>
                <Button variant="outline" onClick={handleClose}>
                  Cancel
                </Button>
                <Button onClick={handleUpload} disabled={!file}>
                  <Upload className="mr-2 h-4 w-4" />
                  Upload & Process
                </Button>
              </>
            )}
            {stage === "complete" && (
              <>
                <Button variant="outline" onClick={reset}>
                  Upload Another
                </Button>
                <Button onClick={handleClose}>
                  Done
                </Button>
              </>
            )}
            {stage === "duplicate" && (
              <>
                <Button variant="outline" onClick={reset}>
                  Upload Different File
                </Button>
                <Button onClick={handleClose}>
                  Done
                </Button>
              </>
            )}
            {stage === "error" && (
              <>
                <Button variant="outline" onClick={handleClose}>
                  Cancel
                </Button>
                <Button onClick={reset}>
                  Try Again
                </Button>
              </>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

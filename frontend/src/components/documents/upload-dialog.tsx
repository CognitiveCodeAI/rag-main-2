"use client";

import * as React from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Upload, X, FileText, CheckCircle, AlertCircle, Info, Loader2, ChevronDown, Clock } from "lucide-react";
import { toast } from "sonner";

import { cn, formatFileSize } from "@/lib/utils";
import {
  extractMetadataPreview,
  processMetadataPreview,
  pollIngestJob,
  embedDocument,
  pollEmbedJob,
  getHealth,
  deleteDocument,
  APIError,
} from "@/lib/api";
import type { Visibility, IngestJob, EmbeddingJob, MetadataPreviewResponse } from "@/lib/api";
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
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
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

interface MetadataFormState {
  doc_date: string;
  year: string;
  source_system: string;
  doc_type: string;
  department: string;
  authority_tier: string;
  effective_from: string;
  effective_to: string;
}

const EMPTY_METADATA_FORM: MetadataFormState = {
  doc_date: "",
  year: "",
  source_system: "",
  doc_type: "",
  department: "",
  authority_tier: "",
  effective_from: "",
  effective_to: "",
};

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

function getApiErrorDetailMessage(detail: unknown): string | null {
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object" && "detail" in detail) {
    const nested = (detail as { detail?: unknown }).detail;
    if (typeof nested === "string") return nested;
  }
  return null;
}

function toInputValue(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "number") return String(value);
  if (typeof value === "string") return value;
  return "";
}

function metadataFormFromPreview(preview: MetadataPreviewResponse): MetadataFormState {
  const extracted = preview.metadata_extracted ?? {};
  return {
    doc_date: toInputValue(extracted.doc_date),
    year: toInputValue(extracted.year),
    source_system: toInputValue(extracted.source_system || "upload"),
    doc_type: toInputValue(extracted.doc_type),
    department: toInputValue(extracted.department),
    authority_tier: toInputValue(extracted.authority_tier),
    effective_from: toInputValue(extracted.effective_from),
    effective_to: toInputValue(extracted.effective_to),
  };
}

function normalizedMetadataFormValue(field: keyof MetadataFormState, value: string): unknown {
  const trimmed = value.trim();
  if (!trimmed) return null;
  if (field === "year" || field === "authority_tier") {
    const n = Number(trimmed);
    return Number.isFinite(n) ? Math.trunc(n) : null;
  }
  return trimmed;
}

export function UploadDialog({ open, onOpenChange, supportedTypes: supportedTypesProp, aclEnabled: aclEnabledProp }: UploadDialogProps) {
  const queryClient = useQueryClient();
  const [isDragging, setIsDragging] = React.useState(false);
  const [file, setFile] = React.useState<File | null>(null);
  const [stage, setStage] = React.useState<UploadStage>("idle");
  const [progress, setProgress] = React.useState(0);
  const [error, setError] = React.useState<string | null>(null);
  const [duplicateInfo, setDuplicateInfo] = React.useState<DuplicateInfo | null>(null);
  const [statusMessage, setStatusMessage] = React.useState<string>("");
  const [startTime, setStartTime] = React.useState<number | null>(null);
  const [elapsed, setElapsed] = React.useState(0);
  const fileInputRef = React.useRef<HTMLInputElement>(null);

  // ACL state — prefer prop from parent, fall back to own fetch
  const [aclEnabledLocal, setAclEnabledLocal] = React.useState(false);
  const [supportedTypesLocal, setSupportedTypesLocal] = React.useState<string[] | null>(null);
  const [workerHealthy, setWorkerHealthy] = React.useState<boolean | null>(null);
  const [workerStatusMessage, setWorkerStatusMessage] = React.useState<string | null>(null);
  const [aclExpanded, setAclExpanded] = React.useState(false);
  const [visibility, setVisibility] = React.useState<Visibility>("public");
  const [allowedRoles, setAllowedRoles] = React.useState<string[]>([]);
  const [allowedGroups, setAllowedGroups] = React.useState<string[]>([]);
  const [allowedUsers, setAllowedUsers] = React.useState<string[]>([]);
  const [previewData, setPreviewData] = React.useState<MetadataPreviewResponse | null>(null);
  const [metadataForm, setMetadataForm] = React.useState<MetadataFormState>(EMPTY_METADATA_FORM);
  const [metadataReviewed, setMetadataReviewed] = React.useState(false);

  // Fetch health for worker availability and optional feature fallback.
  React.useEffect(() => {
    if (!open) return;

    let cancelled = false;
    const syncHealth = () => {
      getHealth(true)
        .then((h) => {
          if (cancelled) return;
          if (aclEnabledProp === undefined) setAclEnabledLocal(!!h.features?.acl_enabled);
          if (supportedTypesProp === undefined && h.features?.supported_file_types?.length) {
            setSupportedTypesLocal(h.features.supported_file_types);
          }
          const workerService = h.services?.celery_worker;
          if (workerService) {
            const healthy = workerService.status === "healthy";
            setWorkerHealthy(healthy);
            setWorkerStatusMessage(workerService.message ?? null);
          } else {
            setWorkerHealthy(null);
            setWorkerStatusMessage(null);
          }
        })
        .catch(() => {
          if (cancelled) return;
          setWorkerHealthy(null);
          setWorkerStatusMessage(null);
        });
    };

    syncHealth();
    const intervalId = window.setInterval(syncHealth, 10000);
    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, [open, aclEnabledProp, supportedTypesProp]);

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
    setDuplicateInfo(null);
    setPreviewData(null);
    setMetadataForm(EMPTY_METADATA_FORM);
    setMetadataReviewed(false);
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
    setPreviewData(null);
    setMetadataForm(EMPTY_METADATA_FORM);
    setMetadataReviewed(false);
    setDuplicateInfo(null);
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

  const handleMetadataFieldChange = (field: keyof MetadataFormState, value: string) => {
    setMetadataForm((prev) => ({ ...prev, [field]: value }));
    setMetadataReviewed(false);
    setError(null);
  };

  const buildMetadataOverrides = (): Record<string, unknown> => {
    if (!previewData) return {};
    const overrides: Record<string, unknown> = {};
    const extracted = previewData.metadata_extracted ?? {};
    const fields: Array<keyof MetadataFormState> = [
      "doc_date",
      "year",
      "source_system",
      "doc_type",
      "department",
      "authority_tier",
      "effective_from",
      "effective_to",
    ];

    for (const field of fields) {
      const current = normalizedMetadataFormValue(field, metadataForm[field]);
      const original = normalizedMetadataFormValue(field, toInputValue(extracted[field]));
      if (current !== original) {
        overrides[field] = current;
      }
    }
    return overrides;
  };

  const handleExtractMetadata = async () => {
    if (!file) return;

    setStage("uploading");
    setStatusMessage("Uploading and extracting metadata...");
    setProgress(15);
    setError(null);
    setDuplicateInfo(null);
    setMetadataReviewed(false);

    try {
      const preview = await extractMetadataPreview(file);
      setPreviewData(preview);
      setMetadataForm(metadataFormFromPreview(preview));
      setStage("idle");
      setProgress(0);
      setStatusMessage("");
      toast.success("Metadata extracted. Review and edit before processing.");
    } catch (e) {
      let errorMessage = e instanceof Error ? e.message : "Failed to extract metadata";
      if (e instanceof APIError && e.status === 415) {
        errorMessage = getApiErrorDetailMessage(e.detail) || "Unsupported file type";
      } else if (e instanceof APIError && e.status === 400) {
        errorMessage = getApiErrorDetailMessage(e.detail) || "Invalid file";
      } else if (e instanceof APIError) {
        errorMessage = getApiErrorDetailMessage(e.detail) || `Metadata extraction failed (HTTP ${e.status})`;
      }
      setStage("error");
      setError(errorMessage);
      toast.error(errorMessage);
    }
  };

  const handleProcess = async () => {
    if (!file || !previewData) return;
    if (!metadataReviewed) {
      setError("Review metadata and confirm before processing.");
      return;
    }
    if (workerHealthy === false) {
      setError(
        workerStatusMessage ||
          "Document processing queue is unavailable. Start a Celery worker and retry."
      );
      return;
    }

    setStartTime(Date.now());
    setElapsed(0);
    let cleanupDocId: string | null = null;
    let shouldAttemptCleanup = false;

    try {
      setStage("ingesting");
      setProgress(15);
      setStatusMessage("Submitting reviewed metadata...");

      const metadata_overrides = buildMetadataOverrides();
      const processPayload = {
        preview_id: previewData.preview_id,
        metadata_overrides,
        ...(aclEnabled ? {
          visibility,
          allowed_roles: visibility === "internal" ? allowedRoles : undefined,
          allowed_groups: visibility === "internal" ? allowedGroups : undefined,
          allowed_users: visibility === "restricted" ? allowedUsers : undefined,
        } : {}),
      };

      let ingestResponse;
      try {
        ingestResponse = await processMetadataPreview(processPayload);
      } catch (e) {
        if (e instanceof APIError && e.status === 409 && typeof e.detail === "object" && e.detail !== null) {
          const body = e.detail as { detail?: string; existing_document?: DuplicateInfo };
          if (body.detail === "duplicate" && body.existing_document) {
            setDuplicateInfo(body.existing_document);
            setStage("duplicate");
            return;
          }
        }
        if (e instanceof APIError && e.status === 503) {
          throw new Error(
            getApiErrorDetailMessage(e.detail) ||
              "Document processing queue is unavailable. Start a Celery worker and retry."
          );
        }
        if (e instanceof APIError && e.status === 410) {
          throw new Error("Metadata preview expired. Re-upload to continue.");
        }
        if (e instanceof APIError) {
          throw new Error(
            getApiErrorDetailMessage(e.detail) ||
            `Failed to start processing (HTTP ${e.status})`
          );
        }
        throw e;
      }

      setStatusMessage("Queued for processing...");
      let ingestResult: IngestJob;
      try {
        ingestResult = await pollIngestJob(ingestResponse.job_id, {
          interval: 2000,
          maxAttempts: 150,
          onProgress: (job: IngestJob) => {
            if (job.pipeline_stage && INGEST_STAGE_LABELS[job.pipeline_stage]) {
              setStatusMessage(INGEST_STAGE_LABELS[job.pipeline_stage]);
            } else if (job.status === "pending") {
              setStatusMessage("Queued, waiting for worker...");
            } else if (job.status === "processing") {
              setStatusMessage("Processing document...");
            }

            if (job.status === "processing") {
              setProgress((prev) => Math.min(48, prev + 3));
            } else if (job.status === "pending") {
              setProgress((prev) => Math.min(20, prev + 1));
            }
          },
        });
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e);
        if (msg.includes("timeout")) {
          throw new Error("Ingestion timed out after 5 minutes. Check the Processing page for job status.");
        }
        throw new Error(`Ingestion failed: ${msg}`);
      }

      cleanupDocId = ingestResult.graph_doc_id || ingestResponse.doc_id;
      shouldAttemptCleanup = !!cleanupDocId;
      setProgress(50);

      setStage("embedding");
      setStatusMessage("Starting embedding generation...");

      let embedResponse;
      try {
        embedResponse = await embedDocument({
          doc_id: cleanupDocId || ingestResponse.doc_id,
          version_id: ingestResult.graph_version !== undefined && ingestResult.graph_version !== null
            ? String(ingestResult.graph_version)
            : ingestResponse.version_id,
        });
      } catch (e) {
        if (e instanceof APIError && e.status === 503) {
          throw new Error(
            getApiErrorDetailMessage(e.detail) ||
              "Embedding queue is unavailable. Start a Celery worker and retry."
          );
        }
        if (e instanceof APIError && e.status === 404) {
          throw new Error("Document nodes not found for embedding. Ingestion may have created an alias for duplicate content.");
        }
        throw new Error(`Failed to start embedding: ${e instanceof Error ? e.message : String(e)}`);
      }
      setProgress(55);

      try {
        await pollEmbedJob(embedResponse.job_id, {
          interval: 3000,
          maxAttempts: 150,
          onProgress: (job: EmbeddingJob) => {
            if (job.pipeline_stage && EMBED_STAGE_LABELS[job.pipeline_stage]) {
              setStatusMessage(EMBED_STAGE_LABELS[job.pipeline_stage]);
            } else if (job.status === "pending") {
              setStatusMessage("Queued for embedding...");
            } else if (job.status === "processing") {
              setStatusMessage("Generating embeddings...");
            }

            if (job.status === "processing" && job.chunk_count) {
              const embedPct = Math.min(95, 55 + ((job.record_count || 0) / job.chunk_count) * 40);
              setProgress(embedPct);
            } else if (job.status === "processing") {
              setProgress((prev) => Math.min(75, prev + 2));
            } else if (job.status === "pending") {
              setProgress((prev) => Math.min(58, prev + 1));
            }
          },
        });
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e);
        if (msg.includes("timeout")) {
          throw new Error("Embedding timed out after 7 minutes. Check the Processing page for job status.");
        }
        throw new Error(`Embedding failed: ${msg}`);
      }

      setProgress(100);
      setStage("complete");
      setStatusMessage("Done!");
      toast.success("Document uploaded and indexed successfully!");
      queryClient.invalidateQueries({ queryKey: ["documents"] });
    } catch (e) {
      let errorMessage = e instanceof Error ? e.message : "Processing failed";
      const timedOut = errorMessage.toLowerCase().includes("timed out");
      if (cleanupDocId && shouldAttemptCleanup && !timedOut) {
        try {
          setStatusMessage("Cleaning up failed document...");
          await deleteDocument(cleanupDocId);
          await Promise.all([
            queryClient.invalidateQueries({ queryKey: ["documents"] }),
            queryClient.invalidateQueries({ queryKey: ["dashboard-documents"] }),
            queryClient.invalidateQueries({ queryKey: ["collections"] }),
          ]);
          errorMessage = `${errorMessage} Partial document data was removed.`;
        } catch (cleanupError) {
          const cleanupMsg = cleanupError instanceof Error ? cleanupError.message : String(cleanupError);
          errorMessage = `${errorMessage} Automatic cleanup failed (${cleanupMsg}). Delete this document manually: ${cleanupDocId}.`;
        }
      }
      setStage("error");
      setError(errorMessage);
      toast.error(errorMessage);
    }
  };

  const getStageLabel = (): string => {
    if (statusMessage) return statusMessage;
    const defaults: Record<UploadStage, string> = {
      idle: "Ready to upload",
      uploading: "Extracting metadata...",
      ingesting: "Processing document...",
      embedding: "Generating embeddings...",
      complete: "Complete!",
      duplicate: "Already processed",
      error: "Error",
    };
    return defaults[stage];
  };

  const metadataWarnings = React.useMemo(() => {
    const warnings = [...(previewData?.warnings ?? [])];
    if (!metadataForm.doc_type.trim()) warnings.push("doc_type is empty.");
    if (!metadataForm.department.trim()) warnings.push("department is empty.");
    if (!metadataForm.authority_tier.trim()) warnings.push("authority_tier is empty.");
    return Array.from(new Set(warnings));
  }, [previewData, metadataForm]);

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Upload Document</DialogTitle>
          <DialogDescription>
            Upload a document, review extracted metadata, then process it into your knowledge base.
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
                onClick={() => {
                  setFile(null);
                  setPreviewData(null);
                  setMetadataForm(EMPTY_METADATA_FORM);
                  setMetadataReviewed(false);
                  setError(null);
                }}
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

          {/* Metadata review form (after preview extraction) */}
          {stage === "idle" && file && previewData && (
            <div className="space-y-3 rounded-lg border p-3">
              <div className="space-y-1">
                <p className="text-sm font-medium">Review Metadata Before Processing</p>
                <p className="text-xs text-muted-foreground">
                  Preview expires at {new Date(previewData.expires_at).toLocaleTimeString()}.
                </p>
              </div>

              {metadataWarnings.length > 0 && (
                <div className="rounded-md bg-amber-500/10 px-3 py-2 text-xs text-amber-700 dark:text-amber-300">
                  <p className="font-medium mb-1">Review warnings</p>
                  <ul className="list-disc pl-4 space-y-0.5">
                    {metadataWarnings.map((warning) => (
                      <li key={warning}>{warning}</li>
                    ))}
                  </ul>
                </div>
              )}

              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <Label htmlFor="meta-doc-type">Doc Type</Label>
                  <Input
                    id="meta-doc-type"
                    value={metadataForm.doc_type}
                    onChange={(e) => handleMetadataFieldChange("doc_type", e.target.value)}
                    placeholder="policy, memo, report..."
                  />
                  <p className="text-[11px] text-muted-foreground">
                    provenance: {previewData.metadata_provenance?.doc_type ?? "none"} | confidence: {(previewData.metadata_confidence?.doc_type ?? 0).toFixed(2)}
                  </p>
                </div>
                <div className="space-y-1">
                  <Label htmlFor="meta-department">Department</Label>
                  <Input
                    id="meta-department"
                    value={metadataForm.department}
                    onChange={(e) => handleMetadataFieldChange("department", e.target.value)}
                    placeholder="legal, engineering..."
                  />
                  <p className="text-[11px] text-muted-foreground">
                    provenance: {previewData.metadata_provenance?.department ?? "none"} | confidence: {(previewData.metadata_confidence?.department ?? 0).toFixed(2)}
                  </p>
                </div>
                <div className="space-y-1">
                  <Label htmlFor="meta-year">Year</Label>
                  <Input
                    id="meta-year"
                    value={metadataForm.year}
                    onChange={(e) => handleMetadataFieldChange("year", e.target.value)}
                    placeholder="2026"
                    inputMode="numeric"
                  />
                </div>
                <div className="space-y-1">
                  <Label htmlFor="meta-authority">Authority Tier</Label>
                  <Select
                    value={metadataForm.authority_tier || "__empty__"}
                    onValueChange={(value) => handleMetadataFieldChange("authority_tier", value === "__empty__" ? "" : value)}
                  >
                    <SelectTrigger id="meta-authority" className="w-full">
                      <SelectValue placeholder="Select tier" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="__empty__">Unknown</SelectItem>
                      <SelectItem value="1">1 (highest)</SelectItem>
                      <SelectItem value="2">2</SelectItem>
                      <SelectItem value="3">3</SelectItem>
                    </SelectContent>
                  </Select>
                  <p className="text-[11px] text-muted-foreground">
                    provenance: {previewData.metadata_provenance?.authority_tier ?? "none"} | confidence: {(previewData.metadata_confidence?.authority_tier ?? 0).toFixed(2)}
                  </p>
                </div>
                <div className="space-y-1">
                  <Label htmlFor="meta-doc-date">Document Date</Label>
                  <Input
                    id="meta-doc-date"
                    type="date"
                    value={metadataForm.doc_date}
                    onChange={(e) => handleMetadataFieldChange("doc_date", e.target.value)}
                  />
                </div>
                <div className="space-y-1">
                  <Label htmlFor="meta-source-system">Source System</Label>
                  <Input
                    id="meta-source-system"
                    value={metadataForm.source_system}
                    onChange={(e) => handleMetadataFieldChange("source_system", e.target.value)}
                    placeholder="upload"
                  />
                </div>
                <div className="space-y-1">
                  <Label htmlFor="meta-effective-from">Effective From</Label>
                  <Input
                    id="meta-effective-from"
                    type="date"
                    value={metadataForm.effective_from}
                    onChange={(e) => handleMetadataFieldChange("effective_from", e.target.value)}
                  />
                </div>
                <div className="space-y-1">
                  <Label htmlFor="meta-effective-to">Effective To</Label>
                  <Input
                    id="meta-effective-to"
                    type="date"
                    value={metadataForm.effective_to}
                    onChange={(e) => handleMetadataFieldChange("effective_to", e.target.value)}
                  />
                </div>
              </div>

              <div className="flex items-center gap-2 pt-1">
                <Checkbox
                  id="metadata-reviewed"
                  checked={metadataReviewed}
                  onCheckedChange={(checked) => setMetadataReviewed(checked === true)}
                />
                <Label htmlFor="metadata-reviewed" className="text-xs font-normal">
                  I reviewed/edited metadata and want to process this document.
                </Label>
              </div>
            </div>
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

          {/* Worker unavailable warning */}
          {stage === "idle" && workerHealthy === false && (
            <div className="flex items-start gap-2 p-3 rounded-lg bg-destructive/10 text-destructive">
              <AlertCircle className="h-5 w-5 shrink-0 mt-0.5" />
              <div className="text-sm space-y-1">
                <p className="font-medium">Processing worker is offline</p>
                <p className="text-xs opacity-90">
                  {workerStatusMessage || "Start a Celery worker to process documents."}
                </p>
              </div>
            </div>
          )}

          {/* Actions */}
          <div className="flex justify-end gap-2">
            {stage === "idle" && !previewData && (
              <>
                <Button variant="outline" onClick={handleClose}>
                  Cancel
                </Button>
                <Button onClick={handleExtractMetadata} disabled={!file}>
                  <Upload className="mr-2 h-4 w-4" />
                  Upload & Extract Metadata
                </Button>
              </>
            )}
            {stage === "idle" && !!previewData && (
              <>
                <Button variant="outline" onClick={handleExtractMetadata} disabled={!file}>
                  Re-Extract
                </Button>
                <Button variant="outline" onClick={handleClose}>
                  Cancel
                </Button>
                <Button
                  onClick={handleProcess}
                  disabled={!file || workerHealthy === false || !metadataReviewed}
                >
                  <Upload className="mr-2 h-4 w-4" />
                  Process Document
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

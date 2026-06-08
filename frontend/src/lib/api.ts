/**
 * API client for NPR RAG backend
 */

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// =============================================================================
// Types
// =============================================================================

export type JobStatus = 
  | "pending" 
  | "queued" 
  | "processing" 
  | "completed" 
  | "partial" 
  | "failed" 
  | "skipped_alias";

export interface Citation {
  page_no: number;
  node_id: string;
  doc_id: string;
  text_snippet?: string;
  text?: string;
  label?: string;
  citation_type?: string;
  authority_tier?: number;
  raw_url?: string;
  bbox?: { x0: number; y0: number; x1: number; y1: number };
  page_size?: { width: number; height: number };
  anchor_snippet?: string;
  source_type?: string;
  mime_type?: string;
  selector_bundle?: SelectorBundle;
  resolve_status?: "exact" | "fuzzy" | "unresolved";
  resolve_reason?: string;
  canonical_view_url?: string;
  source_map_url?: string;
  snapshot_id?: string | null;
  normalization?: string;
  evidence_spans?: EvidenceSpan[];
  evidence_verification?: EvidenceVerification[];
}

export type EvidenceLocator =
  | {
      type: "text_offsets";
      start: number;
      end: number;
    }
  | {
      type: "bbox";
      bbox: { x0: number; y0: number; x1: number; y1: number };
      page_size?: { width: number; height: number };
    };

export interface EvidenceSpan {
  doc_id: string;
  page_index: number; // Explicitly 1-based.
  page_index_base: 1;
  quote_text: string;
  locator: EvidenceLocator;
  confidence: number;
  source_section?: string | null;
}

export interface EvidenceVerification {
  status: "FOUND" | "NOT_FOUND";
  matched_locator?: EvidenceLocator | null;
  confidence: number;
  reason: string;
  doc_id?: string;
  page_index?: number;
}

export interface SelectorBundle {
  schema_version: string;
  node_id: string;
  doc_id: string;
  version: number;
  source_type: string;
  text_position: { start: number; end: number };
  text_quote: { exact: string; prefix: string; suffix: string };
  layout?: {
    page_no?: number;
    bbox?: { x0: number; y0: number; x1: number; y1: number };
    page_size?: { width: number; height: number };
  } | null;
  structural?: Record<string, unknown>;
  normalization: string;
  source_state: {
    content_hash: string;
    mime_type: string;
    source_uri: string;
  };
}

export interface SourceMapNodeEntry {
  node_id: string;
  start: number;
  end: number;
  page_no?: number | null;
  node_type?: string;
  label?: string | null;
}

export interface SourceMapResponse {
  schema_version: string;
  doc_id: string;
  version: number;
  normalization: string;
  generated_at: string;
  canonical_text: string;
  nodes: SourceMapNodeEntry[];
}

export interface SourceManifestResponse {
  doc_id: string;
  version: number;
  raw_url: string;
  mime_type: string;
  canonical_view_available: boolean;
  source_map_available: boolean;
  selectors_available: boolean;
  selector_coverage: {
    nodes_with_selectors: number;
  };
  backfill_needed: boolean;
}

export interface Conflict {
  type: string;
  node_ids: string[];
  description: string;
  resolution?: string;
  source?: string;
}

export interface SeedNode {
  page_no?: number;
  score?: number;
  text?: string;
  relationship?: string;
  label?: string;
  node_id?: string;
  doc_id?: string;
}

export interface AskResponse {
  question: string;
  doc_id: string | null;
  seed_nodes: SeedNode[];
  expanded_nodes: SeedNode[];
  edge_traces: Array<{ from: string; to: string; type: string }>;
  packed_context: string;
  context_node_ids: string[];
  total_context_tokens: number;
  answer: string;
  citations: Citation[];
  model_id: string;
  timing: Record<string, number>;
  metadata_constraints?: Record<string, unknown> | null;
  metadata_filter_applied?: string | null;
  metadata_boosts?: Record<string, number> | null;
  conflicts?: Conflict[] | null;
  has_conflicts: boolean;
  needs_clarification: boolean;
  clarify_prompt?: string | null;
  clarify_options?: string[] | null;
  propagation_safety_mode: boolean;
  propagation_safety_audit?: Record<string, unknown> | null;
  original_question?: string | null;
  llm_rewrite?: {
    used_llm?: boolean;
    original_query?: string;
    rewritten_query?: string;
    reason?: string;
  } | null;
  success: boolean;
  error?: string | null;
}

export interface HealthResponse {
  status: "healthy" | "degraded" | "unhealthy";
  version: string;
  timestamp: string;
  services?: Record<string, { status: "healthy" | "unhealthy" | "unknown"; message?: string }>;
  features?: { acl_enabled?: boolean; supported_file_types?: string[] };
}

export interface DocumentGraph {
  doc_id: string;
  source_uri: string;
  content_hash: string;
  version: number;
  ingested_at: string;
  doc_summary_md?: string | null;
  doc_summary_text?: string | null;
  canonical_doc_id?: string | null;
  embedded_collection_version?: string | null;
  doc_date?: string | null;
  year?: number | null;
  source_system?: string | null;
  doc_type?: string | null;
  department?: string | null;
  authority_tier?: number | null;
  effective_from?: string | null;
  effective_to?: string | null;
  supersedes_doc_id?: string | null;
  node_count?: number | null;
  visibility?: string | null;
  processing_status?: JobStatus | null;
  processing_stage?: string | null;
  processing_error?: string | null;
}

export interface DocumentListResponse {
  items: DocumentGraph[];
  total: number;
  page: number;
  limit: number;
  has_more: boolean;
}

export interface Node {
  node_id: string;
  doc_id: string;
  version: number;
  node_type: string;
  page_no?: number | null;
  chunk_index_in_page?: number | null;
  label?: string | null;
  caption_md?: string | null;
  text_md?: string | null;
  text_plain?: string | null;
  bbox?: Record<string, number> | null;
  content_hash?: string | null;
  meta?: Record<string, unknown> | null;
  created_at: string;
}

export interface NodeListResponse {
  items: Node[];
  total: number;
  page: number;
  limit: number;
  has_more: boolean;
}

export interface IngestJob {
  job_id: string;
  doc_id?: string | null;
  graph_doc_id?: string | null;
  graph_version?: number | null;
  status: JobStatus;
  pipeline_stage?: string | null;
  created_at: string;
  started_at?: string | null;
  completed_at?: string | null;
  error?: string | null;
}

export interface IngestJobListResponse {
  items: IngestJob[];
  total: number;
}

export interface MetadataPreviewResponse {
  preview_id: string;
  filename: string;
  source_type: string;
  mime_type?: string | null;
  expires_at: string;
  metadata_extracted: Record<string, unknown>;
  metadata_provenance: Record<string, string>;
  metadata_confidence: Record<string, number>;
  warnings: string[];
}

export interface EmbeddingJob {
  job_id: string;
  doc_id?: string | null;
  status: JobStatus;
  pipeline_stage?: string | null;
  created_at: string;
  started_at?: string | null;
  completed_at?: string | null;
  chunk_count?: number | null;
  record_count?: number | null;
  total_tokens?: number | null;
  error?: string | null;
}

export interface EmbedJobListResponse {
  items: EmbeddingJob[];
  total: number;
}

export interface RetrievalResult {
  chunk_id: string;
  doc_id: string;
  version_id?: string;
  score: number;
  text?: string;
  text_preview?: string;
  page_no?: number;
  authority_tier?: string;
}

export interface VectorRetrieveResponse {
  query: string;
  view: string;
  results: RetrievalResult[];
  total: number;
}

export interface CollectionStats {
  name: string;
  num_entities: number;
}

export interface CollectionsResponse {
  collections: Record<string, CollectionStats>;
}

// =============================================================================
// API Error Handling
// =============================================================================

export class APIError extends Error {
  constructor(
    message: string,
    public status: number,
    public detail?: unknown
  ) {
    super(message);
    this.name = "APIError";
  }
}

const DEFAULT_TIMEOUT_MS = 30000;

/**
 * fetch() with an AbortController timeout so a stalled request can't hang the
 * UI forever (D5 / audit M-8). Same signature as fetch plus an optional
 * timeoutMs; on timeout it throws an APIError with status 0.
 */
async function fetchWithTimeout(
  input: string,
  init?: RequestInit & { timeoutMs?: number }
): Promise<Response> {
  const { timeoutMs = DEFAULT_TIMEOUT_MS, ...rest } = init ?? {};
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(input, { ...rest, signal: controller.signal });
  } catch (err) {
    if (controller.signal.aborted) {
      throw new APIError(`Request timed out after ${timeoutMs}ms`, 0, input);
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }
}

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let detail: unknown;
    try {
      detail = await response.json();
    } catch {
      detail = await response.text();
    }
    throw new APIError(
      `API request failed: ${response.status} ${response.statusText}`,
      response.status,
      detail
    );
  }
  return response.json();
}

// =============================================================================
// API Functions
// =============================================================================

/**
 * Get system health status
 */
export async function getHealth(checkServices = false): Promise<HealthResponse> {
  const query = checkServices ? "?check_services=true" : "";
  const response = await fetchWithTimeout(`${API_BASE_URL}/health${query}`);
  return handleResponse<HealthResponse>(response);
}

/**
 * Get vector collection statistics
 */
export async function getCollections(): Promise<CollectionsResponse> {
  const response = await fetchWithTimeout(`${API_BASE_URL}/v1/retrieve/collections`);
  return handleResponse<CollectionsResponse>(response);
}

/**
 * Get source/selector artifact availability for a document.
 */
export async function getSourceManifest(docId: string): Promise<SourceManifestResponse> {
  const response = await fetchWithTimeout(`${API_BASE_URL}/v1/documents/${docId}/source-manifest`);
  return handleResponse<SourceManifestResponse>(response);
}

/**
 * Get canonical source map for selector-based highlighting.
 */
export async function getSourceMap(docId: string): Promise<SourceMapResponse> {
  const response = await fetchWithTimeout(`${API_BASE_URL}/v1/documents/${docId}/source-map`);
  return handleResponse<SourceMapResponse>(response);
}

/**
 * List documents with optional filtering
 */
export async function listDocuments(params?: {
  page?: number;
  limit?: number;
  search?: string;
  doc_type?: string;
}): Promise<DocumentListResponse> {
  const searchParams = new URLSearchParams();
  if (params?.page) searchParams.set("page", String(params.page));
  if (params?.limit) searchParams.set("limit", String(params.limit));
  if (params?.search) searchParams.set("search", params.search);
  if (params?.doc_type) searchParams.set("doc_type", params.doc_type);

  const url = `${API_BASE_URL}/v1/documents?${searchParams.toString()}`;
  const response = await fetchWithTimeout(url);
  return handleResponse<DocumentListResponse>(response);
}

/**
 * List nodes for a specific document
 */
export async function listDocumentNodes(
  docId: string,
  params?: {
    page?: number;
    limit?: number;
    node_type?: string;
  }
): Promise<NodeListResponse> {
  const searchParams = new URLSearchParams();
  if (params?.page) searchParams.set("page", String(params.page));
  if (params?.limit) searchParams.set("limit", String(params.limit));
  if (params?.node_type) searchParams.set("node_type", params.node_type);

  const url = `${API_BASE_URL}/v1/documents/${docId}/nodes?${searchParams.toString()}`;
  const response = await fetchWithTimeout(url);
  return handleResponse<NodeListResponse>(response);
}

/**
 * Ask a question about documents
 */
export async function askQuestion(params: {
  question: string;
  doc_id?: string;
  top_k?: number;
  chat_history?: Array<{ role: "user" | "assistant"; content: string }>;
  mode?: "standard" | "propagation_safety";
}): Promise<AskResponse> {
  const response = await fetchWithTimeout(`${API_BASE_URL}/v1/qa/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  return handleResponse<AskResponse>(response);
}

/**
 * Perform vector search
 */
export async function vectorSearch(params: {
  query: string;
  view?: "chunks" | "figures" | "tables";
  top_k?: number;
  doc_id?: string;
}): Promise<VectorRetrieveResponse> {
  const response = await fetchWithTimeout(`${API_BASE_URL}/v1/retrieve/vector`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  return handleResponse<VectorRetrieveResponse>(response);
}

/**
 * List ingestion jobs
 */
export async function listIngestJobs(params?: {
  limit?: number;
  status?: JobStatus;
}): Promise<IngestJobListResponse> {
  const searchParams = new URLSearchParams();
  if (params?.limit) searchParams.set("limit", String(params.limit));
  if (params?.status) searchParams.set("status", params.status);

  const url = `${API_BASE_URL}/v1/ingest/jobs?${searchParams.toString()}`;
  const response = await fetchWithTimeout(url);
  return handleResponse<IngestJobListResponse>(response);
}

/**
 * List embedding jobs
 */
export async function listEmbedJobs(params?: {
  limit?: number;
  status?: JobStatus;
}): Promise<EmbedJobListResponse> {
  const searchParams = new URLSearchParams();
  if (params?.limit) searchParams.set("limit", String(params.limit));
  if (params?.status) searchParams.set("status", params.status);

  const url = `${API_BASE_URL}/v1/embed/jobs?${searchParams.toString()}`;
  const response = await fetchWithTimeout(url);
  return handleResponse<EmbedJobListResponse>(response);
}

/**
 * Upload and ingest a document
 */
export async function ingestDocument(
  file: File,
  options?: {
    visibility?: Visibility;
    allowed_roles?: string[];
    allowed_groups?: string[];
    allowed_users?: string[];
  }
): Promise<{
  doc_id: string;
  version_id: string;
  job_id: string;
}> {
  const formData = new FormData();
  formData.append("file", file);

  if (options?.visibility) {
    formData.append("visibility", options.visibility);
  }
  if (options?.allowed_roles?.length) {
    formData.append("allowed_roles", JSON.stringify(options.allowed_roles));
  }
  if (options?.allowed_groups?.length) {
    formData.append("allowed_groups", JSON.stringify(options.allowed_groups));
  }
  if (options?.allowed_users?.length) {
    formData.append("allowed_users", JSON.stringify(options.allowed_users));
  }

  const response = await fetchWithTimeout(`${API_BASE_URL}/v1/ingest/document`, {
    method: "POST",
    body: formData,
  });
  return handleResponse(response);
}

/**
 * Upload and stage a document, then return extracted metadata preview.
 */
export async function extractMetadataPreview(
  file: File
): Promise<MetadataPreviewResponse> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetchWithTimeout(`${API_BASE_URL}/v1/ingest/metadata-preview`, {
    method: "POST",
    body: formData,
  });
  return handleResponse<MetadataPreviewResponse>(response);
}

/**
 * Process a previously staged metadata preview.
 */
export async function processMetadataPreview(params: {
  preview_id: string;
  metadata_overrides?: Record<string, unknown>;
  ingestion_backend?: "native" | "docling";
  tenant_id?: string;
  visibility?: Visibility;
  allowed_roles?: string[];
  allowed_groups?: string[];
  allowed_users?: string[];
}): Promise<{
  doc_id: string;
  version_id: string;
  job_id: string;
}> {
  const response = await fetchWithTimeout(`${API_BASE_URL}/v1/ingest/process`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  return handleResponse(response);
}

/**
 * Poll an ingestion job until completion
 */
export async function pollIngestJob(
  jobId: string,
  options?: {
    interval?: number;
    maxAttempts?: number;
    onProgress?: (job: IngestJob) => void;
  }
): Promise<IngestJob> {
  const interval = options?.interval || 2000;
  const maxAttempts = options?.maxAttempts || 120;
  let attempts = 0;
  let consecutiveErrors = 0;
  const MAX_CONSECUTIVE_ERRORS = 5;

  while (attempts < maxAttempts) {
    let job: IngestJob;
    try {
      const response = await fetchWithTimeout(`${API_BASE_URL}/v1/ingest/job/${jobId}`);
      job = await handleResponse<IngestJob>(response);
      consecutiveErrors = 0;
    } catch (err) {
      // Circuit breaker: give up after repeated failures instead of polling forever.
      if (++consecutiveErrors >= MAX_CONSECUTIVE_ERRORS) {
        throw err;
      }
      await new Promise((resolve) => setTimeout(resolve, interval));
      attempts++;
      continue;
    }

    options?.onProgress?.(job);

    // Terminal states (skipped_alias is terminal — previously missing, causing
    // alias ingests to poll forever).
    if (
      job.status === "completed" ||
      job.status === "failed" ||
      job.status === "skipped_alias"
    ) {
      if (job.status === "failed") {
        throw new Error(job.error || "Ingestion failed");
      }
      return job;
    }

    await new Promise((resolve) => setTimeout(resolve, interval));
    attempts++;
  }

  throw new Error("Polling timeout exceeded");
}

/**
 * Trigger embedding for a document
 */
export async function embedDocument(params: {
  doc_id: string;
  version_id: string;
}): Promise<{ job_id: string }> {
  const response = await fetchWithTimeout(`${API_BASE_URL}/v1/embed/document`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  return handleResponse(response);
}

/**
 * Poll an embedding job until completion
 */
export async function pollEmbedJob(
  jobId: string,
  options?: {
    interval?: number;
    maxAttempts?: number;
    onProgress?: (job: EmbeddingJob) => void;
  }
): Promise<EmbeddingJob> {
  const interval = options?.interval || 3000;
  const maxAttempts = options?.maxAttempts || 120;
  let attempts = 0;
  let consecutiveErrors = 0;
  const MAX_CONSECUTIVE_ERRORS = 5;

  while (attempts < maxAttempts) {
    let job: EmbeddingJob;
    try {
      const response = await fetchWithTimeout(`${API_BASE_URL}/v1/embed/job/${jobId}`);
      job = await handleResponse<EmbeddingJob>(response);
      consecutiveErrors = 0;
    } catch (err) {
      if (++consecutiveErrors >= MAX_CONSECUTIVE_ERRORS) {
        throw err;
      }
      await new Promise((resolve) => setTimeout(resolve, interval));
      attempts++;
      continue;
    }

    options?.onProgress?.(job);

    if (job.status === "completed" || job.status === "failed" || job.status === "skipped_alias") {
      if (job.status === "failed") {
        throw new Error(job.error || "Embedding failed");
      }
      return job;
    }

    await new Promise((resolve) => setTimeout(resolve, interval));
    attempts++;
  }

  throw new Error("Polling timeout exceeded");
}

// =============================================================================
// Prompt Types
// =============================================================================

export interface PromptMetadata {
  name: string;
  version: string;
  category: string;
  category_label: string;
  filename: string;
  template_variables: string[];
}

export interface PromptDetail {
  name: string;
  version: string;
  category: string;
  category_label: string;
  content: string;
  template_variables: string[];
  all_versions: string[];
}

export interface PromptListResponse {
  prompts: PromptMetadata[];
  categories: Record<string, string>;
}

// =============================================================================
// Prompt API Functions
// =============================================================================

/**
 * List all available prompts
 */
export async function listPrompts(): Promise<PromptListResponse> {
  const response = await fetchWithTimeout(`${API_BASE_URL}/v1/prompts`);
  return handleResponse<PromptListResponse>(response);
}

/**
 * Get a specific prompt by name
 */
export async function getPrompt(
  name: string,
  version?: string
): Promise<PromptDetail> {
  const url = version
    ? `${API_BASE_URL}/v1/prompts/${name}?version=${version}`
    : `${API_BASE_URL}/v1/prompts/${name}`;
  const response = await fetchWithTimeout(url);
  return handleResponse<PromptDetail>(response);
}

/**
 * List all versions available for a prompt
 */
export async function listPromptVersions(name: string): Promise<string[]> {
  const response = await fetchWithTimeout(`${API_BASE_URL}/v1/prompts/${name}/versions`);
  return handleResponse<string[]>(response);
}

// =============================================================================
// ACL Types & Functions
// =============================================================================

export type Visibility = "public" | "internal" | "restricted";

export interface DocumentPolicy {
  doc_id: string;
  tenant_id?: string | null;
  visibility?: string | null;
  allowed_roles?: string[] | null;
  allowed_groups?: string[] | null;
  allowed_users?: string[] | null;
  policy_version?: number | null;
  acl_updated_at?: string | null;
}

export interface PolicyUpdateRequest {
  visibility?: Visibility;
  allowed_roles?: string[];
  allowed_groups?: string[];
  allowed_users?: string[];
}

/**
 * Get ACL policy for a document
 */
export async function getDocumentPolicy(docId: string): Promise<DocumentPolicy> {
  const response = await fetchWithTimeout(`${API_BASE_URL}/v1/acl/documents/${docId}/policy`);
  return handleResponse<DocumentPolicy>(response);
}

/**
 * Update ACL policy for a document
 */
export async function updateDocumentPolicy(
  docId: string,
  policy: PolicyUpdateRequest
): Promise<DocumentPolicy> {
  const response = await fetchWithTimeout(`${API_BASE_URL}/v1/acl/documents/${docId}/policy`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(policy),
  });
  return handleResponse<DocumentPolicy>(response);
}

/**
 * Delete a document and all associated data
 */
export async function deleteDocument(docId: string): Promise<void> {
  const response = await fetchWithTimeout(`${API_BASE_URL}/v1/documents/${docId}`, {
    method: "DELETE",
  });

  if (!response.ok) {
    let detail: unknown;
    try {
      detail = await response.json();
    } catch {
      detail = await response.text();
    }
    throw new APIError(
      `Failed to delete document: ${response.status}`,
      response.status,
      detail
    );
  }
  // 204 No Content - success
}

// =============================================================================
// Settings Types & Functions
// =============================================================================

export interface AppSettings {
  // QA Settings
  enable_llm_query_rewrite: boolean;
  retrieval_top_k: number;
  enable_reranking: boolean;
  rerank_candidate_max: number;
  max_context_tokens: number;

  // Ingestion Settings
  ocr_quality_threshold: number;
  target_chunk_tokens: number;
  chunk_overlap_tokens: number;

  // Metadata
  updated_at?: string | null;
}

export type AppSettingsUpdate = Partial<Omit<AppSettings, "updated_at">>;

/**
 * Get current application settings
 */
export async function getSettings(): Promise<AppSettings> {
  const response = await fetchWithTimeout(`${API_BASE_URL}/v1/settings`);
  return handleResponse<AppSettings>(response);
}

/**
 * Update application settings (partial update)
 */
export async function updateSettings(
  updates: AppSettingsUpdate
): Promise<AppSettings> {
  const response = await fetchWithTimeout(`${API_BASE_URL}/v1/settings`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(updates),
  });
  return handleResponse<AppSettings>(response);
}

/**
 * Reset all settings to defaults
 */
export async function resetSettings(): Promise<AppSettings> {
  const response = await fetchWithTimeout(`${API_BASE_URL}/v1/settings/reset`, {
    method: "POST",
  });
  return handleResponse<AppSettings>(response);
}

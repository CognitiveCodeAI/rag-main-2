"use client";

import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Loader2,
  CheckCircle,
  XCircle,
  Clock,
  RefreshCw,
  FileText,
  Zap,
  BarChart3,
  AlertCircle,
} from "lucide-react";

import { cn, formatRelativeTime, formatDuration, formatNumber } from "@/lib/utils";
import { listIngestJobs, listEmbedJobs } from "@/lib/api";
import type { JobStatus, IngestJob, EmbeddingJob } from "@/lib/api";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Skeleton } from "@/components/ui/skeleton";

// Status badge component
function StatusBadge({ status }: { status: JobStatus }) {
  const config: Record<JobStatus, { variant: "default" | "secondary" | "destructive" | "outline"; icon: React.ElementType; label: string }> = {
    pending: { variant: "outline", icon: Clock, label: "Pending" },
    queued: { variant: "outline", icon: Clock, label: "Queued" },
    processing: { variant: "secondary", icon: Loader2, label: "Processing" },
    completed: { variant: "default", icon: CheckCircle, label: "Completed" },
    partial: { variant: "secondary", icon: CheckCircle, label: "Partial" },
    failed: { variant: "destructive", icon: XCircle, label: "Failed" },
    skipped_alias: { variant: "outline", icon: CheckCircle, label: "Skipped" },
  };
  
  const { variant, icon: Icon, label } = config[status] || config.pending;
  
  return (
    <Badge variant={variant} className="gap-1">
      <Icon className={cn("h-3 w-3", status === "processing" && "animate-spin")} />
      {label}
    </Badge>
  );
}

// Pipeline progress component — driven by real backend pipeline_stage
const INGEST_STAGES = [
  { key: "retrieving_file", label: "Retrieve" },
  { key: "extracting_content", label: "Extract" },
  { key: "chunking", label: "Chunk" },
  { key: "creating_nodes", label: "Nodes" },
  { key: "persisting", label: "Save" },
];

const EMBED_STAGES = [
  { key: "loading_nodes", label: "Load" },
  { key: "generating_embeddings", label: "Embed" },
  { key: "indexing_vectors", label: "Index" },
];

function PipelineProgress({ stage, stages }: { stage?: string | null; stages: { key: string; label: string }[] }) {
  const currentIndex = stage ? stages.findIndex(s => s.key === stage) : -1;

  return (
    <div className="space-y-1">
      <div className="flex items-center gap-1">
        {stages.map((s, i) => (
          <div
            key={s.key}
            className={cn(
              "h-1.5 flex-1 rounded-full transition-colors",
              i <= currentIndex ? "bg-primary" : "bg-muted"
            )}
          />
        ))}
      </div>
      {stage && (
        <p className="text-[10px] text-muted-foreground">
          {stages.find(s => s.key === stage)?.label || stage}
        </p>
      )}
    </div>
  );
}

// Ingest job card component
function IngestJobCard({ job }: { job: IngestJob }) {
  const duration = job.started_at && job.completed_at
    ? new Date(job.completed_at).getTime() - new Date(job.started_at).getTime()
    : null;

  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-start gap-3">
            <div className={cn(
              "p-2 rounded-md",
              job.status === "completed" ? "bg-green-500/10" :
              job.status === "failed" ? "bg-destructive/10" :
              job.status === "processing" ? "bg-primary/10" :
              "bg-muted"
            )}>
              <FileText className="h-5 w-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <p className="font-medium text-sm">
                  {job.doc_id || "Unknown Document"}
                </p>
                <StatusBadge status={job.status} />
              </div>
              <p className="text-xs text-muted-foreground mt-0.5">
                {job.job_id}
              </p>
              
              {/* Error message */}
              {job.error && (
                <p className="text-xs text-destructive mt-2">
                  {job.error}
                </p>
              )}
            </div>
          </div>
          
          <div className="text-right text-xs text-muted-foreground">
            <p>{formatRelativeTime(job.created_at)}</p>
            {duration && (
              <p className="mt-1">{formatDuration(duration)}</p>
            )}
          </div>
        </div>
        
        {/* Progress for processing jobs */}
        {job.status === "processing" && (
          <div className="mt-3">
            <PipelineProgress stage={job.pipeline_stage} stages={INGEST_STAGES} />
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// Embed job card component
function EmbedJobCard({ job }: { job: EmbeddingJob }) {
  const duration = job.started_at && job.completed_at
    ? new Date(job.completed_at).getTime() - new Date(job.started_at).getTime()
    : null;

  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-start gap-3">
            <div className={cn(
              "p-2 rounded-md",
              job.status === "completed" ? "bg-green-500/10" :
              job.status === "failed" ? "bg-destructive/10" :
              job.status === "processing" ? "bg-primary/10" :
              "bg-muted"
            )}>
              <Zap className="h-5 w-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <p className="font-medium text-sm">
                  {job.doc_id || "Unknown Document"}
                </p>
                <StatusBadge status={job.status} />
              </div>
              <p className="text-xs text-muted-foreground mt-0.5">
                {job.job_id}
              </p>
              
              {/* Stats for completed embed jobs */}
              {job.status === "completed" && (
                <div className="flex items-center gap-4 mt-2 text-xs text-muted-foreground">
                  {job.chunk_count && (
                    <span>{job.chunk_count} chunks</span>
                  )}
                  {job.total_tokens && (
                    <span>{formatNumber(job.total_tokens)} tokens</span>
                  )}
                </div>
              )}
              
              {/* Error message */}
              {job.error && (
                <p className="text-xs text-destructive mt-2">
                  {job.error}
                </p>
              )}
            </div>
          </div>

          <div className="text-right text-xs text-muted-foreground">
            <p>{formatRelativeTime(job.created_at)}</p>
            {duration && (
              <p className="mt-1">{formatDuration(duration)}</p>
            )}
          </div>
        </div>

        {/* Progress for processing embed jobs */}
        {job.status === "processing" && (
          <div className="mt-3">
            <PipelineProgress stage={job.pipeline_stage} stages={EMBED_STAGES} />
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// Stats card
interface StatsCardProps {
  title: string;
  value: string | number;
  description: string;
  icon: React.ElementType;
  loading?: boolean;
}

function StatsCard({ title, value, description, icon: Icon, loading }: StatsCardProps) {
  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm text-muted-foreground">{title}</p>
            {loading ? (
              <Skeleton className="h-8 w-16 mt-1" />
            ) : (
              <p className="text-2xl font-bold">{value}</p>
            )}
            <p className="text-xs text-muted-foreground">{description}</p>
          </div>
          <Icon className="h-8 w-8 text-muted-foreground/50" />
        </div>
      </CardContent>
    </Card>
  );
}

export default function ProcessingPage() {
  const [lastRefresh, setLastRefresh] = React.useState(new Date());

  // Fetch ingest jobs
  const { 
    data: ingestData, 
    isLoading: ingestLoading, 
    isError: ingestError,
    refetch: refetchIngest 
  } = useQuery({
    queryKey: ["ingestJobs"],
    queryFn: () => listIngestJobs({ limit: 50 }),
    refetchInterval: 10000, // Auto-refresh every 10 seconds
  });

  // Fetch embed jobs
  const { 
    data: embedData, 
    isLoading: embedLoading,
    isError: embedError, 
    refetch: refetchEmbed 
  } = useQuery({
    queryKey: ["embedJobs"],
    queryFn: () => listEmbedJobs({ limit: 50 }),
    refetchInterval: 10000,
  });

  const handleRefresh = React.useCallback(async () => {
    await Promise.all([refetchIngest(), refetchEmbed()]);
    setLastRefresh(new Date());
  }, [refetchIngest, refetchEmbed]);

  // Calculate stats
  const ingestJobs = ingestData?.items || [];
  const embedJobs = embedData?.items || [];

  const ingestStats = {
    total: ingestData?.total || 0,
    completed: ingestJobs.filter(j => j.status === "completed").length,
    processing: ingestJobs.filter(j => j.status === "processing" || j.status === "pending").length,
  };

  const embedStats = {
    total: embedData?.total || 0,
    completed: embedJobs.filter(j => j.status === "completed").length,
    totalTokens: embedJobs.reduce((sum, j) => sum + (j.total_tokens || 0), 0),
  };

  const isRefreshing = ingestLoading || embedLoading;

  return (
    <div className="flex flex-col gap-6 p-6">
      {/* Page header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Processing</h1>
          <p className="text-muted-foreground">
            Monitor document ingestion and embedding jobs
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground">
            Last updated: {formatRelativeTime(lastRefresh.toISOString())}
          </span>
          <Button
            variant="outline"
            size="sm"
            onClick={handleRefresh}
            disabled={isRefreshing}
          >
            <RefreshCw className={cn("h-4 w-4 mr-2", isRefreshing && "animate-spin")} />
            Refresh
          </Button>
        </div>
      </div>

      {/* Stats grid */}
      <div className="grid gap-4 md:grid-cols-4">
        <StatsCard
          title="Ingest Jobs"
          value={ingestStats.total}
          description={`${ingestStats.completed} completed`}
          icon={FileText}
          loading={ingestLoading}
        />
        <StatsCard
          title="Processing"
          value={ingestStats.processing}
          description="Active jobs"
          icon={Loader2}
          loading={ingestLoading}
        />
        <StatsCard
          title="Embed Jobs"
          value={embedStats.total}
          description={`${embedStats.completed} completed`}
          icon={Zap}
          loading={embedLoading}
        />
        <StatsCard
          title="Tokens Processed"
          value={formatNumber(embedStats.totalTokens)}
          description="Total embeddings"
          icon={BarChart3}
          loading={embedLoading}
        />
      </div>

      {/* Jobs tabs */}
      <Tabs defaultValue="ingest" className="space-y-4">
        <TabsList>
          <TabsTrigger value="ingest" className="gap-2">
            <FileText className="h-4 w-4" />
            Ingestion Jobs
            {ingestStats.processing > 0 && (
              <Badge variant="secondary" className="ml-1">
                {ingestStats.processing}
              </Badge>
            )}
          </TabsTrigger>
          <TabsTrigger value="embed" className="gap-2">
            <Zap className="h-4 w-4" />
            Embedding Jobs
          </TabsTrigger>
        </TabsList>

        <TabsContent value="ingest" className="space-y-4">
          {ingestLoading ? (
            <div className="space-y-3">
              {[...Array(3)].map((_, i) => (
                <Skeleton key={i} className="h-24 w-full" />
              ))}
            </div>
          ) : ingestError ? (
            <Card>
              <CardContent className="flex flex-col items-center justify-center py-12">
                <AlertCircle className="h-12 w-12 text-destructive mb-4" />
                <p className="text-sm text-muted-foreground">
                  Failed to load ingestion jobs
                </p>
                <Button variant="outline" size="sm" onClick={() => refetchIngest()} className="mt-4">
                  Try Again
                </Button>
              </CardContent>
            </Card>
          ) : ingestJobs.length === 0 ? (
            <Card>
              <CardContent className="flex flex-col items-center justify-center py-12">
                <FileText className="h-12 w-12 text-muted-foreground mb-4" />
                <p className="text-sm text-muted-foreground">
                  No ingestion jobs found
                </p>
              </CardContent>
            </Card>
          ) : (
            <div className="space-y-3">
              {ingestJobs.map((job) => (
                <IngestJobCard key={job.job_id} job={job} />
              ))}
            </div>
          )}
        </TabsContent>

        <TabsContent value="embed" className="space-y-4">
          {embedLoading ? (
            <div className="space-y-3">
              {[...Array(3)].map((_, i) => (
                <Skeleton key={i} className="h-24 w-full" />
              ))}
            </div>
          ) : embedError ? (
            <Card>
              <CardContent className="flex flex-col items-center justify-center py-12">
                <AlertCircle className="h-12 w-12 text-destructive mb-4" />
                <p className="text-sm text-muted-foreground">
                  Failed to load embedding jobs
                </p>
                <Button variant="outline" size="sm" onClick={() => refetchEmbed()} className="mt-4">
                  Try Again
                </Button>
              </CardContent>
            </Card>
          ) : embedJobs.length === 0 ? (
            <Card>
              <CardContent className="flex flex-col items-center justify-center py-12">
                <Zap className="h-12 w-12 text-muted-foreground mb-4" />
                <p className="text-sm text-muted-foreground">
                  No embedding jobs found
                </p>
              </CardContent>
            </Card>
          ) : (
            <div className="space-y-3">
              {embedJobs.map((job) => (
                <EmbedJobCard key={job.job_id} job={job} />
              ))}
            </div>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}

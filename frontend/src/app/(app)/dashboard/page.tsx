"use client";

import * as React from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import {
  FileText,
  MessageSquare,
  Database,
  Upload,
  ArrowRight,
  Activity,
  CheckCircle,
  XCircle,
  Clock,
} from "lucide-react";

import { cn, formatRelativeTime, formatNumber, getFilename } from "@/lib/utils";
import { getHealth, getCollections, listDocuments } from "@/lib/api";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";

// Metric card component
interface MetricCardProps {
  title: string;
  value: string | number;
  description?: string;
  icon: React.ElementType;
  trend?: "up" | "down" | "neutral";
  loading?: boolean;
}

function MetricCard({ title, value, description, icon: Icon, loading }: MetricCardProps) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium">{title}</CardTitle>
        <Icon className="h-4 w-4 text-muted-foreground" />
      </CardHeader>
      <CardContent>
        {loading ? (
          <>
            <Skeleton className="h-7 w-20 mb-1" />
            <Skeleton className="h-4 w-32" />
          </>
        ) : (
          <>
            <div className="text-2xl font-bold">{value}</div>
            {description && (
              <p className="text-xs text-muted-foreground">{description}</p>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}

// Quick action button component
interface QuickActionProps {
  title: string;
  description: string;
  icon: React.ElementType;
  href: string;
}

function QuickAction({ title, description, icon: Icon, href }: QuickActionProps) {
  return (
    <Link href={href}>
      <Card className="hover:bg-accent/50 transition-colors cursor-pointer group">
        <CardContent className="flex items-center gap-4 p-4">
          <div className="bg-primary/10 p-3 rounded-lg group-hover:bg-primary/20 transition-colors">
            <Icon className="h-6 w-6 text-primary" />
          </div>
          <div className="flex-1">
            <h3 className="font-semibold">{title}</h3>
            <p className="text-sm text-muted-foreground">{description}</p>
          </div>
          <ArrowRight className="h-5 w-5 text-muted-foreground group-hover:text-primary transition-colors" />
        </CardContent>
      </Card>
    </Link>
  );
}

// Status indicator
function StatusIndicator({ status }: { status: "healthy" | "unhealthy" | "unknown" }) {
  const config = {
    healthy: { icon: CheckCircle, color: "text-green-500", label: "Healthy" },
    unhealthy: { icon: XCircle, color: "text-destructive", label: "Unhealthy" },
    unknown: { icon: Clock, color: "text-muted-foreground", label: "Unknown" },
  };
  const { icon: Icon, color, label } = config[status];

  return (
    <div className="flex items-center gap-2">
      <Icon className={cn("h-4 w-4", color)} />
      <span className={cn("text-sm", color)}>{label}</span>
    </div>
  );
}

export default function DashboardPage() {
  // Fetch health status
  const { data: health, isLoading: healthLoading, isError: healthError } = useQuery({
    queryKey: ["health", "services"],
    queryFn: () => getHealth(true),
    refetchInterval: 30000,
  });

  // Fetch collections stats
  const { data: collections, isLoading: collectionsLoading } = useQuery({
    queryKey: ["collections"],
    queryFn: getCollections,
    refetchInterval: 60000,
  });

  // Fetch documents list
  const { data: documentsData, isLoading: documentsLoading } = useQuery({
    queryKey: ["dashboard-documents"],
    queryFn: () => listDocuments({ limit: 10 }),
    refetchInterval: 60000,
  });

  // Calculate total vectors
  const totalVectors = React.useMemo(() => {
    if (!collections?.collections) return 0;
    return Object.values(collections.collections).reduce(
      (sum, col) => sum + (col.num_entities || 0),
      0
    );
  }, [collections]);

  const workerService = health?.services?.celery_worker;
  const apiStatus: "healthy" | "unhealthy" | "unknown" = healthLoading
    ? "unknown"
    : healthError
    ? "unhealthy"
    : "healthy";
  const queueStatus: "healthy" | "unhealthy" | "unknown" =
    workerService?.status === "healthy"
      ? "healthy"
      : workerService?.status === "unhealthy"
      ? "unhealthy"
      : "unknown";

  const systemStatusLabel =
    health?.status === "healthy"
      ? "Online"
      : health?.status === "degraded"
      ? "Degraded"
      : "Offline";

  return (
    <div className="flex flex-col gap-6 p-6">
      {/* Page header */}
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Dashboard</h1>
        <p className="text-muted-foreground">
          Overview of your RAG system and quick actions
        </p>
      </div>

      {/* Metrics grid */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <MetricCard
          title="System Status"
          value={systemStatusLabel}
          description={health ? `Version ${health.version}` : "Connecting..."}
          icon={Activity}
          loading={healthLoading}
        />
        <MetricCard
          title="Total Vectors"
          value={formatNumber(totalVectors)}
          description="Across all collections"
          icon={Database}
          loading={collectionsLoading}
        />
        <MetricCard
          title="Collections"
          value={collections?.collections ? Object.keys(collections.collections).length : 0}
          description="Active vector indices"
          icon={FileText}
          loading={collectionsLoading}
        />
        <MetricCard
          title="Last Updated"
          value={health ? formatRelativeTime(health.timestamp) : "—"}
          description="System health check"
          icon={Clock}
          loading={healthLoading}
        />
      </div>

      {/* Quick actions */}
      <div>
        <h2 className="text-lg font-semibold mb-4">Quick Actions</h2>
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          <QuickAction
            title="Upload Document"
            description="Add a new document to the system"
            icon={Upload}
            href="/documents?upload=true"
          />
          <QuickAction
            title="Start Chat"
            description="Ask questions about your documents"
            icon={MessageSquare}
            href="/chat"
          />
          <QuickAction
            title="View Documents"
            description="Browse and manage your files"
            icon={FileText}
            href="/documents"
          />
        </div>
      </div>

      {/* System status */}
      <div className="grid gap-4 md:grid-cols-2">
        {/* Services status */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Service Status</CardTitle>
            <CardDescription>Current system health</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {healthLoading ? (
              <div className="space-y-3">
                <Skeleton className="h-6 w-full" />
                <Skeleton className="h-6 w-full" />
                <Skeleton className="h-6 w-full" />
              </div>
            ) : (
              <>
                <div className="flex items-center justify-between">
                  <span className="text-sm">API Server</span>
                  <StatusIndicator status={apiStatus} />
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm">Vector Database</span>
                  <StatusIndicator
                    status={collections ? "healthy" : "unknown"}
                  />
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm">Processing Queue</span>
                  <StatusIndicator status={queueStatus} />
                </div>
                {workerService?.message && (
                  <p className="text-xs text-muted-foreground">
                    {workerService.message}
                  </p>
                )}
              </>
            )}
          </CardContent>
        </Card>

        {/* Collections breakdown */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Vector Collections</CardTitle>
            <CardDescription>Index statistics</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {collectionsLoading ? (
              <div className="space-y-3">
                <Skeleton className="h-6 w-full" />
                <Skeleton className="h-6 w-full" />
              </div>
            ) : collections?.collections ? (
              Object.entries(collections.collections).map(([name, stats]) => (
                <div key={name} className="flex items-center justify-between">
                  <div>
                    <span className="text-sm font-medium">{name}</span>
                    <p className="text-xs text-muted-foreground">
                      {stats.name}
                    </p>
                  </div>
                  <Badge variant="outline">
                    {formatNumber(stats.num_entities)} vectors
                  </Badge>
                </div>
              ))
            ) : (
              <p className="text-sm text-muted-foreground">
                No collections found
              </p>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Processed Documents */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <div>
            <CardTitle className="text-base">Processed Documents</CardTitle>
            <CardDescription>Files ingested into the system</CardDescription>
          </div>
          <Button variant="outline" size="sm" asChild>
            <Link href="/documents">View All</Link>
          </Button>
        </CardHeader>
        <CardContent>
          {documentsLoading ? (
            <div className="space-y-3">
              <Skeleton className="h-12 w-full" />
              <Skeleton className="h-12 w-full" />
              <Skeleton className="h-12 w-full" />
            </div>
          ) : documentsData?.items && documentsData.items.length > 0 ? (
            <div className="space-y-3">
              {documentsData.items.map((doc) => (
                <div
                  key={doc.doc_id}
                  className="flex items-center justify-between p-3 rounded-lg border bg-card hover:bg-accent/50 transition-colors"
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <div className="bg-primary/10 p-2 rounded-md shrink-0">
                      <FileText className="h-4 w-4 text-primary" />
                    </div>
                    <div className="min-w-0">
                      <p className="text-sm font-medium truncate">
                        {getFilename(doc.source_uri)}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {doc.node_count ? `${doc.node_count} chunks` : "Processing..."} 
                        {doc.year && doc.year > 0 ? ` • ${doc.year}` : ""}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    {doc.doc_type && (
                      <Badge variant="secondary" className="text-xs">
                        {doc.doc_type}
                      </Badge>
                    )}
                    <Badge variant="outline" className="text-xs">
                      {formatRelativeTime(doc.ingested_at)}
                    </Badge>
                  </div>
                </div>
              ))}
              {documentsData.total > documentsData.items.length && (
                <p className="text-xs text-muted-foreground text-center pt-2">
                  +{documentsData.total - documentsData.items.length} more documents
                </p>
              )}
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center py-8 text-center">
              <FileText className="h-8 w-8 text-muted-foreground mb-4" />
              <p className="text-sm text-muted-foreground">
                No documents have been processed yet.
              </p>
              <Button variant="link" size="sm" asChild className="mt-2">
                <Link href="/documents?upload=true">Upload your first document →</Link>
              </Button>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

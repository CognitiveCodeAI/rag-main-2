"use client";

import * as React from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Settings,
  MessageSquare,
  FileText,
  RotateCcw,
  Save,
  Loader2,
  AlertCircle,
} from "lucide-react";
import { toast } from "sonner";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Slider } from "@/components/ui/slider";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription } from "@/components/ui/alert";

import {
  getSettings,
  updateSettings,
  resetSettings,
  type AppSettings,
  type AppSettingsUpdate,
} from "@/lib/api";

interface SettingRowProps {
  label: string;
  description: string;
  children: React.ReactNode;
}

function SettingRow({ label, description, children }: SettingRowProps) {
  return (
    <div className="flex items-center justify-between py-4">
      <div className="space-y-0.5 pr-4">
        <Label className="text-base">{label}</Label>
        <p className="text-sm text-muted-foreground">{description}</p>
      </div>
      <div className="flex-shrink-0">{children}</div>
    </div>
  );
}

interface SliderSettingProps {
  label: string;
  description: string;
  value: number;
  min: number;
  max: number;
  step: number;
  unit?: string;
  onChange: (value: number) => void;
}

function SliderSetting({
  label,
  description,
  value,
  min,
  max,
  step,
  unit = "",
  onChange,
}: SliderSettingProps) {
  return (
    <div className="py-4 space-y-3">
      <div className="flex items-center justify-between">
        <div className="space-y-0.5">
          <Label className="text-base">{label}</Label>
          <p className="text-sm text-muted-foreground">{description}</p>
        </div>
        <span className="font-mono text-sm bg-muted px-2 py-1 rounded">
          {value}
          {unit}
        </span>
      </div>
      <Slider
        value={[value]}
        min={min}
        max={max}
        step={step}
        onValueChange={([v]) => onChange(v)}
        className="w-full"
      />
      <div className="flex justify-between text-xs text-muted-foreground">
        <span>
          {min}
          {unit}
        </span>
        <span>
          {max}
          {unit}
        </span>
      </div>
    </div>
  );
}

function SettingsLoadingSkeleton() {
  return (
    <div className="flex flex-col gap-6 p-6">
      <div>
        <Skeleton className="h-9 w-32" />
        <Skeleton className="h-5 w-64 mt-2" />
      </div>
      <div className="grid gap-6 md:grid-cols-2">
        {[1, 2].map((i) => (
          <Card key={i}>
            <CardHeader>
              <Skeleton className="h-6 w-48" />
              <Skeleton className="h-4 w-64 mt-1" />
            </CardHeader>
            <CardContent className="space-y-4">
              {[1, 2, 3].map((j) => (
                <div key={j} className="flex justify-between py-4">
                  <div className="space-y-2">
                    <Skeleton className="h-5 w-40" />
                    <Skeleton className="h-4 w-56" />
                  </div>
                  <Skeleton className="h-5 w-9" />
                </div>
              ))}
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}

export default function SettingsPage() {
  const queryClient = useQueryClient();

  // Local state for pending changes
  const [localSettings, setLocalSettings] = React.useState<AppSettings | null>(
    null
  );
  const [hasChanges, setHasChanges] = React.useState(false);

  // Fetch settings
  const {
    data: serverSettings,
    isLoading,
    isError,
    error,
  } = useQuery({
    queryKey: ["settings"],
    queryFn: getSettings,
    staleTime: 30000, // Consider fresh for 30s
  });

  // Sync local state when server data loads
  React.useEffect(() => {
    if (serverSettings && !localSettings) {
      setLocalSettings(serverSettings);
    }
  }, [serverSettings, localSettings]);

  // Update mutation
  const updateMutation = useMutation({
    mutationFn: updateSettings,
    onSuccess: (data) => {
      queryClient.setQueryData(["settings"], data);
      setLocalSettings(data);
      setHasChanges(false);
      toast.success("Settings saved successfully");
    },
    onError: (err) => {
      toast.error(`Failed to save settings: ${err.message}`);
    },
  });

  // Reset mutation
  const resetMutation = useMutation({
    mutationFn: resetSettings,
    onSuccess: (data) => {
      queryClient.setQueryData(["settings"], data);
      setLocalSettings(data);
      setHasChanges(false);
      toast.success("Settings reset to defaults");
    },
    onError: (err) => {
      toast.error(`Failed to reset settings: ${err.message}`);
    },
  });

  // Update local setting and mark as changed
  const updateLocal = (key: keyof AppSettingsUpdate, value: unknown) => {
    if (!localSettings) return;
    setLocalSettings({ ...localSettings, [key]: value });
    setHasChanges(true);
  };

  // Save changes
  const handleSave = () => {
    if (!localSettings || !serverSettings) return;

    // Build diff of changed values
    const updates: AppSettingsUpdate = {};
    const keys: (keyof AppSettingsUpdate)[] = [
      "enable_llm_query_rewrite",
      "retrieval_top_k",
      "enable_reranking",
      "rerank_candidate_max",
      "max_context_tokens",
      "ocr_quality_threshold",
      "target_chunk_tokens",
      "chunk_overlap_tokens",
    ];

    for (const key of keys) {
      if (localSettings[key] !== serverSettings[key]) {
        (updates as Record<string, unknown>)[key] = localSettings[key];
      }
    }

    if (Object.keys(updates).length > 0) {
      updateMutation.mutate(updates);
    } else {
      setHasChanges(false);
      toast.info("No changes to save");
    }
  };

  // Reset to defaults
  const handleReset = () => {
    if (
      confirm("Are you sure you want to reset all settings to their defaults?")
    ) {
      resetMutation.mutate();
    }
  };

  // Discard local changes
  const handleDiscard = () => {
    if (serverSettings) {
      setLocalSettings(serverSettings);
      setHasChanges(false);
    }
  };

  if (isLoading) {
    return <SettingsLoadingSkeleton />;
  }

  if (isError) {
    return (
      <div className="flex flex-col gap-6 p-6">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Settings</h1>
          <p className="text-muted-foreground">
            System configuration and settings
          </p>
        </div>
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>
            Failed to load settings: {(error as Error)?.message || "Unknown error"}
          </AlertDescription>
        </Alert>
      </div>
    );
  }

  if (!localSettings) {
    return <SettingsLoadingSkeleton />;
  }

  const isSaving = updateMutation.isPending || resetMutation.isPending;

  return (
    <div className="flex flex-col gap-6 p-6">
      {/* Page header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Settings</h1>
          <p className="text-muted-foreground">
            Configure application behavior at runtime
          </p>
        </div>
        <div className="flex items-center gap-2">
          {hasChanges && (
            <Button variant="ghost" onClick={handleDiscard} disabled={isSaving}>
              Discard
            </Button>
          )}
          <Button
            variant="outline"
            onClick={handleReset}
            disabled={isSaving}
            className="gap-2"
          >
            {resetMutation.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <RotateCcw className="h-4 w-4" />
            )}
            Reset to Defaults
          </Button>
          <Button
            onClick={handleSave}
            disabled={!hasChanges || isSaving}
            className="gap-2"
          >
            {updateMutation.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Save className="h-4 w-4" />
            )}
            Save Changes
          </Button>
        </div>
      </div>

      {hasChanges && (
        <Alert>
          <Settings className="h-4 w-4" />
          <AlertDescription>
            You have unsaved changes. Click &quot;Save Changes&quot; to apply them.
          </AlertDescription>
        </Alert>
      )}

      <div className="grid gap-6 md:grid-cols-2">
        {/* Question Answering Settings */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <MessageSquare className="h-5 w-5" />
              Question Answering
            </CardTitle>
            <CardDescription>
              Configure how questions are processed and answered
            </CardDescription>
          </CardHeader>
          <CardContent>
            <SettingRow
              label="LLM Query Rewriting"
              description="Use AI to rewrite follow-up questions for better context"
            >
              <Switch
                checked={localSettings.enable_llm_query_rewrite}
                onCheckedChange={(checked) =>
                  updateLocal("enable_llm_query_rewrite", checked)
                }
              />
            </SettingRow>

            <Separator />

            <SettingRow
              label="Reranking"
              description="Use cross-encoder model to improve result relevance"
            >
              <Switch
                checked={localSettings.enable_reranking}
                onCheckedChange={(checked) =>
                  updateLocal("enable_reranking", checked)
                }
              />
            </SettingRow>

            <Separator />

            <SliderSetting
              label="Retrieval Top-K"
              description="Number of results from vector search"
              value={localSettings.retrieval_top_k}
              min={1}
              max={50}
              step={1}
              onChange={(v) => updateLocal("retrieval_top_k", v)}
            />

            <Separator />

            <SliderSetting
              label="Rerank Candidates"
              description="Maximum candidates to consider for reranking"
              value={localSettings.rerank_candidate_max}
              min={5}
              max={50}
              step={1}
              onChange={(v) => updateLocal("rerank_candidate_max", v)}
            />

            <Separator />

            <SliderSetting
              label="Max Context Tokens"
              description="Maximum tokens in the LLM context window"
              value={localSettings.max_context_tokens}
              min={1000}
              max={32000}
              step={500}
              onChange={(v) => updateLocal("max_context_tokens", v)}
            />
          </CardContent>
        </Card>

        {/* Document Ingestion Settings */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <FileText className="h-5 w-5" />
              Document Ingestion
            </CardTitle>
            <CardDescription>
              Configure how documents are processed and chunked
            </CardDescription>
          </CardHeader>
          <CardContent>
            <SliderSetting
              label="OCR Quality Threshold"
              description="Text quality below this triggers OCR fallback"
              value={localSettings.ocr_quality_threshold}
              min={0}
              max={1}
              step={0.05}
              onChange={(v) => updateLocal("ocr_quality_threshold", v)}
            />

            <Separator />

            <SliderSetting
              label="Target Chunk Tokens"
              description="Target size for document chunks"
              value={localSettings.target_chunk_tokens}
              min={100}
              max={2000}
              step={50}
              unit=" tokens"
              onChange={(v) => updateLocal("target_chunk_tokens", v)}
            />

            <Separator />

            <SliderSetting
              label="Chunk Overlap"
              description="Token overlap between adjacent chunks"
              value={localSettings.chunk_overlap_tokens}
              min={0}
              max={500}
              step={10}
              unit=" tokens"
              onChange={(v) => updateLocal("chunk_overlap_tokens", v)}
            />

            <Separator />

            {/* Info section */}
            <div className="py-4 rounded-lg">
              <p className="text-sm text-muted-foreground">
                Changes to ingestion settings apply to newly processed
                documents. Existing documents retain their original chunking.
              </p>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Last updated */}
      {serverSettings?.updated_at && (
        <p className="text-xs text-muted-foreground text-center">
          Settings last updated:{" "}
          {new Date(serverSettings.updated_at).toLocaleString()}
        </p>
      )}
    </div>
  );
}

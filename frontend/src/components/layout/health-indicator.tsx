"use client";

import * as React from "react";
import { Activity, AlertCircle, CheckCircle, Loader2 } from "lucide-react";

import { cn } from "@/lib/utils";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { getHealth } from "@/lib/api";
import type { HealthResponse } from "@/lib/api";

type HealthStatus = "healthy" | "unhealthy" | "loading" | "error";

export function HealthIndicator() {
  const [status, setStatus] = React.useState<HealthStatus>("loading");
  const [health, setHealth] = React.useState<HealthResponse | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  const checkHealthStatus = React.useCallback(async () => {
    try {
      const response = await getHealth();
      setHealth(response);
      setStatus(response.status === "healthy" ? "healthy" : "unhealthy");
      setError(null);
    } catch (e) {
      setStatus("error");
      setError(e instanceof Error ? e.message : "Connection failed");
      setHealth(null);
    }
  }, []);

  React.useEffect(() => {
    // Initial check
    checkHealthStatus();

    // Poll every 30 seconds
    const interval = setInterval(checkHealthStatus, 30000);

    return () => clearInterval(interval);
  }, [checkHealthStatus]);

  const statusConfig = {
    healthy: {
      icon: CheckCircle,
      color: "text-green-500",
      bgColor: "bg-green-500/10",
      label: "System Healthy",
    },
    unhealthy: {
      icon: AlertCircle,
      color: "text-yellow-500",
      bgColor: "bg-yellow-500/10",
      label: "System Unhealthy",
    },
    loading: {
      icon: Loader2,
      color: "text-muted-foreground",
      bgColor: "bg-muted",
      label: "Checking...",
    },
    error: {
      icon: AlertCircle,
      color: "text-destructive",
      bgColor: "bg-destructive/10",
      label: "Connection Error",
    },
  };

  const config = statusConfig[status];
  const Icon = config.icon;

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          onClick={checkHealthStatus}
          className={cn(
            "flex items-center gap-1.5 rounded-full px-2 py-1 text-xs transition-colors",
            config.bgColor,
            "hover:opacity-80"
          )}
        >
          <Icon
            className={cn(
              "h-3.5 w-3.5",
              config.color,
              status === "loading" && "animate-spin"
            )}
          />
          <span className={cn("hidden sm:inline-block", config.color)}>
            {status === "healthy" ? "Online" : status === "loading" ? "..." : "Offline"}
          </span>
        </button>
      </TooltipTrigger>
      <TooltipContent side="bottom" align="end">
        <div className="flex flex-col gap-1">
          <div className="flex items-center gap-2">
            <Activity className="h-3.5 w-3.5" />
            <span className="font-medium">{config.label}</span>
          </div>
          {health && (
            <>
              <p className="text-xs text-muted-foreground">
                Version: {health.version}
              </p>
              <p className="text-xs text-muted-foreground">
                Last checked: {new Date(health.timestamp).toLocaleTimeString()}
              </p>
            </>
          )}
          {error && (
            <p className="text-xs text-destructive">{error}</p>
          )}
          <p className="text-xs text-muted-foreground mt-1">
            Click to refresh
          </p>
        </div>
      </TooltipContent>
    </Tooltip>
  );
}

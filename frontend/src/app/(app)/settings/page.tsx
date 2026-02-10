"use client";

import * as React from "react";
import { Settings, Server, Database, Cpu, Info } from "lucide-react";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";

export default function SettingsPage() {
  return (
    <div className="flex flex-col gap-6 p-6">
      {/* Page header */}
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Settings</h1>
        <p className="text-muted-foreground">
          System configuration and settings
        </p>
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        {/* API Configuration */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Server className="h-5 w-5" />
              API Configuration
            </CardTitle>
            <CardDescription>
              Backend connection settings
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex justify-between items-center">
              <span className="text-sm">API URL</span>
              <code className="text-xs bg-muted px-2 py-1 rounded">
                {process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}
              </code>
            </div>
            <Separator />
            <div className="flex justify-between items-center">
              <span className="text-sm">Connection</span>
              <Badge variant="outline">Active</Badge>
            </div>
          </CardContent>
        </Card>

        {/* System Info */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Info className="h-5 w-5" />
              System Information
            </CardTitle>
            <CardDescription>
              Application version and build info
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex justify-between items-center">
              <span className="text-sm">Frontend Version</span>
              <Badge>0.1.0</Badge>
            </div>
            <Separator />
            <div className="flex justify-between items-center">
              <span className="text-sm">Framework</span>
              <span className="text-sm text-muted-foreground">Next.js 16</span>
            </div>
          </CardContent>
        </Card>

        {/* Storage */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Database className="h-5 w-5" />
              Storage
            </CardTitle>
            <CardDescription>
              Data storage configuration
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex justify-between items-center">
              <span className="text-sm">Vector Database</span>
              <span className="text-sm text-muted-foreground">Milvus</span>
            </div>
            <Separator />
            <div className="flex justify-between items-center">
              <span className="text-sm">Object Storage</span>
              <span className="text-sm text-muted-foreground">MinIO</span>
            </div>
            <Separator />
            <div className="flex justify-between items-center">
              <span className="text-sm">Metadata</span>
              <span className="text-sm text-muted-foreground">PostgreSQL</span>
            </div>
          </CardContent>
        </Card>

        {/* Processing */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Cpu className="h-5 w-5" />
              Processing
            </CardTitle>
            <CardDescription>
              Background task configuration
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex justify-between items-center">
              <span className="text-sm">Task Queue</span>
              <span className="text-sm text-muted-foreground">Celery + Redis</span>
            </div>
            <Separator />
            <div className="flex justify-between items-center">
              <span className="text-sm">Embedding Model</span>
              <span className="text-sm text-muted-foreground">text-embedding-3-large</span>
            </div>
            <Separator />
            <div className="flex justify-between items-center">
              <span className="text-sm">LLM Model</span>
              <span className="text-sm text-muted-foreground">GPT-4</span>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Note */}
      <Card className="bg-muted/50">
        <CardContent className="flex items-center gap-4 py-4">
          <Info className="h-5 w-5 text-muted-foreground" />
          <p className="text-sm text-muted-foreground">
            Configuration is read-only. To modify settings, update the backend environment variables.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}

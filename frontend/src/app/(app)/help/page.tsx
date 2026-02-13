"use client";

import * as React from "react";
import {
  HelpCircle,
  FileText,
  MessageSquare,
  Upload,
  Search,
  Keyboard,
  ExternalLink,
} from "lucide-react";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

interface HelpSectionProps {
  title: string;
  description: string;
  icon: React.ElementType;
  items: string[];
}

function HelpSection({ title, description, icon: Icon, items }: HelpSectionProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Icon className="h-5 w-5" />
          {title}
        </CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent>
        <ul className="space-y-2">
          {items.map((item, i) => (
            <li key={i} className="flex items-start gap-2 text-sm">
              <span className="text-primary mt-1">•</span>
              {item}
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}

export default function HelpPage() {
  return (
    <div className="flex flex-col gap-6 p-6">
      {/* Page header */}
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Help</h1>
        <p className="text-muted-foreground">
          Learn how to use Near Perfect RAG effectively
        </p>
      </div>

      {/* Help sections */}
      <div className="grid gap-6 md:grid-cols-2">
        <HelpSection
          title="Uploading Documents"
          description="Add documents to your knowledge base"
          icon={Upload}
          items={[
            "Click 'Upload Document' or press ⌘U",
            "Drag and drop files or click to browse",
            "Supported formats: PDF, DOCX, TXT, MD, CSV, XLSX",
            "Maximum file size: 50MB",
            "Documents are automatically processed and indexed",
          ]}
        />

        <HelpSection
          title="Chatting with Documents"
          description="Ask questions about your content"
          icon={MessageSquare}
          items={[
            "Select a document from the dropdown",
            "Type your question and press Enter",
            "Click on citations to view source details",
            "Use the Sources panel to explore context",
            "Conflicts are highlighted when detected",
          ]}
        />

        <HelpSection
          title="Searching"
          description="Find relevant content across documents"
          icon={Search}
          items={[
            "Use semantic search for meaning-based queries",
            "Choose between Content and Contextual views",
            "Adjust the number of results as needed",
            "Click results to view more details",
          ]}
        />

        <HelpSection
          title="Managing Documents"
          description="Browse and organize your files"
          icon={FileText}
          items={[
            "View all documents in the Documents page",
            "Filter by type, department, or status",
            "Use search to find specific files",
            "Re-index documents if needed",
          ]}
        />
      </div>

      {/* Keyboard shortcuts */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Keyboard className="h-5 w-5" />
            Keyboard Shortcuts
          </CardTitle>
          <CardDescription>Quick actions to boost productivity</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {[
              { keys: ["⌘", "K"], description: "Open command palette" },
              { keys: ["⌘", "B"], description: "Toggle sidebar" },
              { keys: ["⌘", "U"], description: "Upload document" },
              { keys: ["⌘", "N"], description: "New chat" },
              { keys: ["Enter"], description: "Send message" },
              { keys: ["Shift", "Enter"], description: "New line in chat" },
            ].map((shortcut, i) => (
              <div key={i} className="flex items-center justify-between">
                <span className="text-sm">{shortcut.description}</span>
                <div className="flex items-center gap-1">
                  {shortcut.keys.map((key, j) => (
                    <React.Fragment key={j}>
                      <kbd className="px-2 py-1 text-xs bg-muted rounded border">
                        {key}
                      </kbd>
                      {j < shortcut.keys.length - 1 && (
                        <span className="text-muted-foreground">+</span>
                      )}
                    </React.Fragment>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Additional resources */}
      <Card className="bg-muted/50">
        <CardContent className="flex items-center justify-between py-4">
          <div className="flex items-center gap-3">
            <HelpCircle className="h-5 w-5 text-muted-foreground" />
            <div>
              <p className="font-medium text-sm">Need more help?</p>
              <p className="text-xs text-muted-foreground">
                Visit our website or contact support
              </p>
            </div>
          </div>
          <a href="https://cognitivecode.ai" target="_blank" rel="noopener noreferrer">
            <Badge variant="outline" className="cursor-pointer hover:bg-accent">
              <ExternalLink className="h-3 w-3 mr-1" />
              cognitivecode.ai
            </Badge>
          </a>
        </CardContent>
      </Card>
    </div>
  );
}

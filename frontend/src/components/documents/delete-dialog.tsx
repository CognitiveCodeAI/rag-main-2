"use client";

import * as React from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2, AlertTriangle, CheckCircle2 } from "lucide-react";
import { toast } from "sonner";

import { deleteDocument } from "@/lib/api";
import type { DocumentGraph } from "@/lib/api";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface DeleteDialogProps {
  document: DocumentGraph | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

// Deletion steps shown during progress
const DELETION_STEPS = [
  { label: "Removing vector embeddings", duration: 800 },
  { label: "Deleting stored files", duration: 600 },
  { label: "Removing document metadata", duration: 400 },
  { label: "Cleaning up graph nodes", duration: 500 },
  { label: "Finalizing deletion", duration: 300 },
];

export function DeleteDialog({ document, open, onOpenChange }: DeleteDialogProps) {
  const queryClient = useQueryClient();
  const [currentStep, setCurrentStep] = React.useState(-1);
  const [completedSteps, setCompletedSteps] = React.useState<number[]>([]);

  // Reset progress when dialog opens/closes
  React.useEffect(() => {
    if (!open) {
      setCurrentStep(-1);
      setCompletedSteps([]);
    }
  }, [open]);

  // Animate through steps when deletion is in progress
  React.useEffect(() => {
    if (currentStep < 0) return;

    if (currentStep < DELETION_STEPS.length) {
      const timer = setTimeout(() => {
        setCompletedSteps(prev => [...prev, currentStep]);
        setCurrentStep(prev => prev + 1);
      }, DELETION_STEPS[currentStep].duration);

      return () => clearTimeout(timer);
    }
  }, [currentStep]);

  const mutation = useMutation({
    mutationFn: () => deleteDocument(document!.doc_id),
    onMutate: () => {
      // Start the progress animation
      setCurrentStep(0);
      setCompletedSteps([]);
    },
    onSuccess: () => {
      // Mark all steps complete
      setCompletedSteps(DELETION_STEPS.map((_, i) => i));

      // Short delay to show completion, then close
      setTimeout(() => {
        toast.success("Document deleted successfully");
        queryClient.invalidateQueries({ queryKey: ["documents"] });
        queryClient.invalidateQueries({ queryKey: ["dashboard-documents"] });
        onOpenChange(false);
      }, 500);
    },
    onError: (err: Error) => {
      setCurrentStep(-1);
      setCompletedSteps([]);
      toast.error(err.message || "Failed to delete document");
    },
  });

  const filename = document?.source_uri
    ?.replace("upload://", "")
    ?.replace("file://", "")
    ?.split("/")
    ?.pop() || "this document";

  const isDeleting = mutation.isPending;

  return (
    <Dialog open={open} onOpenChange={isDeleting ? undefined : onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-destructive">
            <AlertTriangle className="h-5 w-5" />
            Delete Document
          </DialogTitle>
          <DialogDescription>
            {isDeleting
              ? "Please wait while the document is being removed..."
              : "This action cannot be undone. This will permanently delete:"
            }
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3 py-4">
          {!isDeleting ? (
            <>
              <p className="font-medium text-sm">{filename}</p>
              <ul className="text-sm text-muted-foreground space-y-1 list-disc list-inside">
                <li>All document content and metadata</li>
                <li>All indexed chunks and embeddings</li>
                <li>All associated graph nodes and edges</li>
              </ul>
            </>
          ) : (
            <div className="space-y-2">
              <p className="font-medium text-sm mb-3">{filename}</p>
              {DELETION_STEPS.map((step, index) => {
                const isComplete = completedSteps.includes(index);
                const isCurrent = currentStep === index;
                const isPending = index > currentStep;

                return (
                  <div
                    key={index}
                    className={cn(
                      "flex items-center gap-3 text-sm py-1.5 px-2 rounded transition-all duration-300",
                      isComplete && "text-muted-foreground",
                      isCurrent && "bg-primary/10 text-primary",
                      isPending && "text-muted-foreground/50"
                    )}
                  >
                    {isComplete ? (
                      <CheckCircle2 className="h-4 w-4 text-green-500 shrink-0" />
                    ) : isCurrent ? (
                      <Loader2 className="h-4 w-4 animate-spin shrink-0" />
                    ) : (
                      <div className="h-4 w-4 rounded-full border border-muted-foreground/30 shrink-0" />
                    )}
                    <span>{step.label}</span>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        <DialogFooter className="gap-2 sm:gap-0">
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={isDeleting}
          >
            Cancel
          </Button>
          <Button
            variant="destructive"
            onClick={() => mutation.mutate()}
            disabled={isDeleting}
          >
            {isDeleting ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Deleting...
              </>
            ) : (
              "Delete Document"
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

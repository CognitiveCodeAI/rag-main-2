"use client";

import * as React from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";

import type { Visibility, PolicyUpdateRequest } from "@/lib/api";
import { getDocumentPolicy, updateDocumentPolicy } from "@/lib/api";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { TagInput } from "@/components/ui/tag-input";

interface PermissionsDialogProps {
  docId: string | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function PermissionsDialog({ docId, open, onOpenChange }: PermissionsDialogProps) {
  const queryClient = useQueryClient();

  const [visibility, setVisibility] = React.useState<Visibility>("public");
  const [allowedRoles, setAllowedRoles] = React.useState<string[]>([]);
  const [allowedGroups, setAllowedGroups] = React.useState<string[]>([]);
  const [allowedUsers, setAllowedUsers] = React.useState<string[]>([]);

  const { data: policy, isLoading, isError } = useQuery({
    queryKey: ["document-policy", docId],
    queryFn: () => getDocumentPolicy(docId!),
    enabled: !!docId && open,
  });

  // Sync form state when policy loads
  React.useEffect(() => {
    if (policy) {
      setVisibility((policy.visibility as Visibility) || "public");
      setAllowedRoles(policy.allowed_roles || []);
      setAllowedGroups(policy.allowed_groups || []);
      setAllowedUsers(policy.allowed_users || []);
    }
  }, [policy]);

  const mutation = useMutation({
    mutationFn: (req: PolicyUpdateRequest) => updateDocumentPolicy(docId!, req),
    onSuccess: () => {
      toast.success("Permissions updated");
      queryClient.invalidateQueries({ queryKey: ["document-policy", docId] });
      queryClient.invalidateQueries({ queryKey: ["documents"] });
      onOpenChange(false);
    },
    onError: (err: Error) => {
      toast.error(err.message || "Failed to update permissions");
    },
  });

  const handleSave = () => {
    if (visibility === "internal" && allowedRoles.length === 0 && allowedGroups.length === 0) {
      toast.error("Internal visibility requires at least one role or group");
      return;
    }
    if (visibility === "restricted" && allowedUsers.length === 0) {
      toast.error("Restricted visibility requires at least one user");
      return;
    }

    mutation.mutate({
      visibility,
      allowed_roles: visibility === "internal" ? allowedRoles : [],
      allowed_groups: visibility === "internal" ? allowedGroups : [],
      allowed_users: visibility === "restricted" ? allowedUsers : [],
    });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Document Permissions</DialogTitle>
          <DialogDescription>
            Control who can access this document.
          </DialogDescription>
        </DialogHeader>

        {isLoading ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          </div>
        ) : isError ? (
          <div className="py-8 text-center text-sm text-destructive">
            Failed to load policy. The ACL endpoint may require admin headers.
          </div>
        ) : (
          <div className="space-y-4">
            <div className="space-y-2">
              <p className="text-sm font-medium">Visibility</p>
              <Select value={visibility} onValueChange={(v) => setVisibility(v as Visibility)}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="public">Public — any tenant user</SelectItem>
                  <SelectItem value="internal">Internal — matching role or group</SelectItem>
                  <SelectItem value="restricted">Restricted — explicit users only</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {visibility === "internal" && (
              <>
                <div className="space-y-2">
                  <p className="text-sm font-medium">Allowed Roles</p>
                  <TagInput
                    value={allowedRoles}
                    onChange={setAllowedRoles}
                    placeholder="Type a role and press Enter"
                  />
                </div>
                <div className="space-y-2">
                  <p className="text-sm font-medium">Allowed Groups</p>
                  <TagInput
                    value={allowedGroups}
                    onChange={setAllowedGroups}
                    placeholder="Type a group and press Enter"
                  />
                </div>
              </>
            )}

            {visibility === "restricted" && (
              <div className="space-y-2">
                <p className="text-sm font-medium">Allowed Users</p>
                <TagInput
                  value={allowedUsers}
                  onChange={setAllowedUsers}
                  placeholder="Type a user ID and press Enter"
                />
              </div>
            )}

            {policy?.policy_version != null && (
              <p className="text-xs text-muted-foreground">
                Policy version {policy.policy_version}
                {policy.acl_updated_at && ` · Updated ${new Date(policy.acl_updated_at).toLocaleDateString()}`}
              </p>
            )}

            <div className="flex justify-end gap-2 pt-2">
              <Button variant="outline" onClick={() => onOpenChange(false)}>
                Cancel
              </Button>
              <Button onClick={handleSave} disabled={mutation.isPending}>
                {mutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                Save
              </Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

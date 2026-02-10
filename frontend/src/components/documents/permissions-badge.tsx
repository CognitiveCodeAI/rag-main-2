"use client";

import { Shield, Users, Lock } from "lucide-react";
import { Badge } from "@/components/ui/badge";

const config: Record<string, { label: string; icon: typeof Shield; className: string }> = {
  public: {
    label: "Public",
    icon: Shield,
    className: "bg-green-500/10 text-green-700 dark:text-green-400 border-green-500/20",
  },
  internal: {
    label: "Internal",
    icon: Users,
    className: "bg-yellow-500/10 text-yellow-700 dark:text-yellow-400 border-yellow-500/20",
  },
  restricted: {
    label: "Restricted",
    icon: Lock,
    className: "bg-red-500/10 text-red-700 dark:text-red-400 border-red-500/20",
  },
};

export function PermissionsBadge({ visibility }: { visibility?: string | null }) {
  if (!visibility) return <span className="text-muted-foreground">—</span>;

  const c = config[visibility];
  if (!c) return <Badge variant="outline">{visibility}</Badge>;

  const Icon = c.icon;
  return (
    <Badge variant="outline" className={c.className}>
      <Icon className="h-3 w-3" />
      {c.label}
    </Badge>
  );
}

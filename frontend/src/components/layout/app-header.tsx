"use client";

import * as React from "react";
import { usePathname } from "next/navigation";
import { Search, Command } from "lucide-react";

import { cn } from "@/lib/utils";
import { SidebarTrigger } from "@/components/ui/sidebar";
import { Separator } from "@/components/ui/separator";
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { HealthIndicator } from "./health-indicator";
import { APP_NAME } from "@/lib/brand";

// Route name mapping
const routeNames: Record<string, string> = {
  dashboard: "Dashboard",
  documents: "Documents",
  chat: "Chat",
  processing: "Processing",
  search: "Search",
  prompts: "Prompts",
  settings: "Settings",
  about: "About",
  help: "Help",
  inspect: "Inspect",
};

interface AppHeaderProps {
  onCommandOpen?: () => void;
}

export function AppHeader({ onCommandOpen }: AppHeaderProps) {
  const pathname = usePathname();

  // Generate breadcrumb items from pathname
  const breadcrumbItems = React.useMemo(() => {
    const segments = pathname.split("/").filter(Boolean);
    const items: { label: string; href: string; isLast: boolean }[] = [];

    segments.forEach((segment, index) => {
      const href = "/" + segments.slice(0, index + 1).join("/");
      const label = routeNames[segment] || decodeURIComponent(segment);
      items.push({
        label,
        href,
        isLast: index === segments.length - 1,
      });
    });

    return items;
  }, [pathname]);

  return (
    <header className="sticky top-0 z-50 flex h-14 shrink-0 items-center gap-2 border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60 px-4">
      <SidebarTrigger className="-ml-1" />
      <Separator orientation="vertical" className="h-4" />

      {/* Breadcrumbs */}
      <Breadcrumb className="hidden md:flex">
        <BreadcrumbList>
          {breadcrumbItems.map((item, index) => (
            <React.Fragment key={item.href}>
              {index > 0 && <BreadcrumbSeparator />}
              <BreadcrumbItem>
                {item.isLast ? (
                  <BreadcrumbPage className="font-medium">
                    {item.label}
                  </BreadcrumbPage>
                ) : (
                  <BreadcrumbLink href={item.href}>{item.label}</BreadcrumbLink>
                )}
              </BreadcrumbItem>
            </React.Fragment>
          ))}
        </BreadcrumbList>
      </Breadcrumb>

      {/* Test environment marker */}
      <span className="hidden lg:inline-flex ml-3 rounded-md border border-amber-500/40 bg-amber-500/10 px-2 py-1 text-[11px] font-semibold uppercase tracking-wide text-amber-300">
        Test UI Only: This UI is for pipeline testing. Create any UX/UI you need.
      </span>

      {/* Mobile title */}
      <span className="font-medium md:hidden">
        {breadcrumbItems[breadcrumbItems.length - 1]?.label || APP_NAME}
      </span>

      {/* Spacer */}
      <div className="flex-1" />

      {/* Right side actions */}
      <div className="flex items-center gap-2">
        {/* Health indicator */}
        <HealthIndicator />

        {/* Command palette trigger */}
        <Button
          variant="outline"
          size="sm"
          className={cn(
            "relative h-8 w-full justify-start rounded-md bg-muted/50 text-sm font-normal text-muted-foreground shadow-none sm:pr-12 md:w-40 lg:w-64"
          )}
          onClick={onCommandOpen}
        >
          <Search className="mr-2 h-4 w-4" />
          <span className="hidden lg:inline-flex">Search everything...</span>
          <span className="inline-flex lg:hidden">Search...</span>
          <kbd className="pointer-events-none absolute right-1.5 top-1.5 hidden h-5 select-none items-center gap-1 rounded border bg-muted px-1.5 font-mono text-[10px] font-medium opacity-100 sm:flex">
            <Command className="h-3 w-3" />K
          </kbd>
        </Button>
      </div>
    </header>
  );
}

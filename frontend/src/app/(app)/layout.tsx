"use client";

import * as React from "react";
import Link from "next/link";
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";
import { AppSidebar, AppHeader, CommandMenu } from "@/components/layout";
import { BRAND } from "@/lib/brand";

export default function AppLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const [commandOpen, setCommandOpen] = React.useState(false);

  return (
    <SidebarProvider>
      <AppSidebar />
      <SidebarInset className="flex min-h-svh flex-col">
        <AppHeader onCommandOpen={() => setCommandOpen(true)} />
        <main className="flex-1 overflow-auto">
          {children}
        </main>
        <footer className="border-t px-4 py-2 text-xs text-muted-foreground">
          Built by {BRAND.companyName} —{" "}
          <Link
            href={BRAND.website}
            target="_blank"
            rel="noopener noreferrer"
            className="hover:text-foreground transition-colors"
          >
            {BRAND.websiteLabel}
          </Link>
        </footer>
      </SidebarInset>
      <CommandMenu open={commandOpen} onOpenChange={setCommandOpen} />
    </SidebarProvider>
  );
}

"use client";

import * as React from "react";
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";
import { AppSidebar, AppHeader, CommandMenu } from "@/components/layout";

export default function AppLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const [commandOpen, setCommandOpen] = React.useState(false);

  return (
    <SidebarProvider>
      <AppSidebar />
      <SidebarInset>
        <AppHeader onCommandOpen={() => setCommandOpen(true)} />
        <main className="flex-1 overflow-auto">
          {children}
        </main>
      </SidebarInset>
      <CommandMenu open={commandOpen} onOpenChange={setCommandOpen} />
    </SidebarProvider>
  );
}

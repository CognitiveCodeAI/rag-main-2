"use client";

import dynamic from "next/dynamic";
import { Skeleton } from "@/components/ui/skeleton";

// Dynamically import the chat client with SSR disabled to avoid hydration issues
const ChatClient = dynamic(() => import("./chat-client"), {
  ssr: false,
  loading: () => (
    <div className="flex flex-col h-[calc(100vh-3.5rem)]">
      {/* Header skeleton */}
      <div className="flex items-center justify-between px-4 py-3 border-b">
        <Skeleton className="h-9 w-[300px]" />
        <Skeleton className="h-9 w-24" />
      </div>
      
      {/* Content skeleton */}
      <div className="flex-1 flex items-center justify-center">
        <div className="flex flex-col items-center gap-4">
          <Skeleton className="h-16 w-16 rounded-full" />
          <Skeleton className="h-6 w-40" />
          <Skeleton className="h-4 w-64" />
        </div>
      </div>
      
      {/* Input skeleton */}
      <div className="border-t p-4">
        <div className="max-w-3xl mx-auto">
          <Skeleton className="h-20 w-full" />
        </div>
      </div>
    </div>
  ),
});

export default function ChatPage() {
  return <ChatClient />;
}

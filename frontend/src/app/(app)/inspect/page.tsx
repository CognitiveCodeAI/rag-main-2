"use client";

import dynamic from "next/dynamic";
import { Skeleton } from "@/components/ui/skeleton";

// Dynamically import the inspect client with SSR disabled to avoid hydration issues
const InspectClient = dynamic(() => import("./inspect-client"), {
  ssr: false,
  loading: () => (
    <div className="flex flex-col h-[calc(100vh-3.5rem)]">
      {/* Header skeleton */}
      <div className="p-6 pb-4">
        <Skeleton className="h-9 w-32 mb-2" />
        <Skeleton className="h-5 w-64" />
      </div>
      
      {/* Selector skeleton */}
      <div className="px-6 pb-4">
        <Skeleton className="h-9 w-full max-w-md" />
      </div>
      
      {/* Content skeleton */}
      <div className="flex-1 flex items-center justify-center">
        <div className="text-center">
          <Skeleton className="h-16 w-16 mx-auto mb-4" />
          <Skeleton className="h-6 w-40 mx-auto mb-2" />
          <Skeleton className="h-4 w-64 mx-auto" />
        </div>
      </div>
    </div>
  ),
});

export default function InspectPage() {
  return <InspectClient />;
}

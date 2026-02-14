import type { Metadata } from "next";
import Link from "next/link";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { APP_NAME, BRAND } from "@/lib/brand";

export const metadata: Metadata = {
  title: "About",
};

export default function AboutPage() {
  return (
    <div className="flex flex-col gap-6 p-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">About</h1>
        <p className="text-muted-foreground">
          Ownership and product attribution.
        </p>
      </div>

      <Card className="max-w-2xl">
        <CardHeader>
          <CardTitle>{APP_NAME}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          <p>
            Developed by {BRAND.developer}
          </p>
          <p>{BRAND.companyName}</p>
          <Link
            href={BRAND.website}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex text-primary hover:underline"
          >
            {BRAND.website}
          </Link>
        </CardContent>
      </Card>
    </div>
  );
}

import type { Metadata } from "next";
import { ThemeProvider } from "@/themes";
import { QueryProvider } from "@/components/providers";
import { Toaster } from "@/components/ui/sonner";
import "./globals.css";

export const metadata: Metadata = {
  title: "Near Perfect RAG — by Cognitive Code™",
  description: "AI-powered document intelligence with evidence-based citations. Built by Cognitive Code™ — Custom Software. AI at the Core.",
  keywords: ["AI", "RAG", "retrieval augmented generation", "document intelligence", "citations", "Cognitive Code", "NPR"],
  authors: [{ name: "Cognitive Code™", url: "https://cognitivecode.ai" }],
  openGraph: {
    title: "Near Perfect RAG — by Cognitive Code™",
    description: "AI-powered document intelligence with evidence-based citations.",
    url: "https://cognitivecode.ai",
    siteName: "Cognitive Code™",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "Near Perfect RAG — by Cognitive Code™",
    description: "AI-powered document intelligence with evidence-based citations",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="antialiased min-h-screen" suppressHydrationWarning>
        <ThemeProvider defaultTheme="dark" enableSystem>
          <QueryProvider>
            {children}
            <Toaster richColors position="bottom-right" />
          </QueryProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}

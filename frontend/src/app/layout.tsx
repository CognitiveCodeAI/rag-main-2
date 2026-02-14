import type { Metadata } from "next";
import { ThemeProvider } from "@/themes";
import { QueryProvider } from "@/components/providers";
import { Toaster } from "@/components/ui/sonner";
import { APP_NAME, BRAND, BROWSER_TITLE } from "@/lib/brand";
import "./globals.css";

export const metadata: Metadata = {
  applicationName: APP_NAME,
  title: {
    default: BROWSER_TITLE,
    template: `%s — ${BRAND.companyName}`,
  },
  description: "Evidence-first document intelligence with grounded citations.",
  keywords: ["AI", "RAG", "retrieval augmented generation", "document intelligence", "citations", BRAND.companyName, "NPR"],
  authors: [{ name: BRAND.companyName, url: BRAND.website }],
  creator: BRAND.companyName,
  publisher: BRAND.companyName,
  openGraph: {
    title: BROWSER_TITLE,
    description: "Evidence-first document intelligence with grounded citations.",
    url: BRAND.website,
    siteName: BRAND.companyName,
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: BROWSER_TITLE,
    description: "Evidence-first document intelligence with grounded citations.",
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

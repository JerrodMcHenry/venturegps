import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { ClerkProvider } from "@clerk/nextjs";

import AppShell from "@/components/layout/AppShell";
import ThemeProvider from "@/components/providers/ThemeProvider";

import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

// Portfolio Release Task 6 -- Standardize User-Facing Terminology:
// "Startup Intelligence Engine"/"Startup Power Score" were the product's
// old public-facing names -- every page that doesn't set its own
// explicit <title> (via generateMetadata) fell back to this site-wide
// default, so the browser tab/search-result title disagreed with the
// VentureGPS branding the homepage and nav already use (Portfolio
// Release Task 4). SIE remains the correct INTERNAL engine name (see
// CLAUDE.md, app/docs/SIE_Methodology_v1.md) -- this is a user-facing
// display change only, not a rename of the engine itself.
export const metadata: Metadata = {
  title: {
    default: "VentureGPS",
    template: "%s | VentureGPS",
  },
  description: "Evidence-backed startup analysis, powered by the VentureGPS Score.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={`${geistSans.variable} ${geistMono.variable}`}
    >
      <body className="min-h-screen bg-background font-sans text-foreground antialiased">
        {/* SIE Authentication Phase 1: ClerkProvider wraps the whole app,
            same placement Clerk's own current Next.js App Router
            quickstart uses (inside <body>, outside everything else) --
            preserves the existing ThemeProvider/AppShell structure and
            styling untouched underneath it. */}
        <ClerkProvider>
          <ThemeProvider>
            <AppShell>{children}</AppShell>
          </ThemeProvider>
        </ClerkProvider>
      </body>
    </html>
  );
}

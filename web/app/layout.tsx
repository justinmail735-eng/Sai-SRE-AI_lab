import type { Metadata } from "next";
import { headers } from "next/headers";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export async function generateMetadata(): Promise<Metadata> {
  const requestHeaders = await headers();
  const host = requestHeaders.get("x-forwarded-host") ?? requestHeaders.get("host") ?? "localhost:3000";
  const protocol = requestHeaders.get("x-forwarded-proto") ?? (host.startsWith("localhost") ? "http" : "https");
  const image = `${protocol}://${host}/sentinel-sre-og-v2.png`;

  return {
    title: "SentinelSRE — Reliability engineering, with receipts",
    description: "A verified SRE portfolio: live telemetry, governed incident agents, Kubernetes recovery, and plan-tested AWS and Azure foundations.",
    icons: { icon: "/favicon.svg", shortcut: "/favicon.svg" },
    openGraph: { title: "SentinelSRE — Reliability engineering, with receipts", description: "Live telemetry, governed agents, Kubernetes recovery, and multi-cloud infrastructure evidence.", images: [image] },
    twitter: { card: "summary_large_image", title: "SentinelSRE — Reliability engineering, with receipts", description: "A runnable enterprise SRE lab with verified evidence.", images: [image] },
  };
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased`}
      >
        {children}
      </body>
    </html>
  );
}

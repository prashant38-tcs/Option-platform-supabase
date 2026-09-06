import type { Metadata } from "next";
import type { ReactNode } from "react";
import "./globals.css";

export const metadata: Metadata = {
  title: "Options Trading Platform",
  description: "Multi-Agent Autonomous Options Trading Platform -- NSE Index Options",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-background text-gray-200 antialiased">{children}</body>
    </html>
  );
}

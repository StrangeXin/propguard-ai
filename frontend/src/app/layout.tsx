import type { Metadata } from "next";
import "./globals.css";
import { Providers } from "./providers";

export const metadata: Metadata = {
  title: "PropGuard AI — Prop Firm Risk Monitor",
  description: "AI-powered prop firm compliance monitoring and signal intelligence",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="min-h-full flex flex-col bg-zinc-950 text-white font-sans">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}

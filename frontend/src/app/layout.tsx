import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Warmstart · Redis Vector Firewall",
  description:
    "Live demonstration of an AI cost & latency firewall: Redis vector cache vs direct LLM inference.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className="antialiased">{children}</body>
    </html>
  );
}
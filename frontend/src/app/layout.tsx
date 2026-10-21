import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "DevRelay AI · Engineering Handoff",
  description: "Static repository intelligence and evidence-backed engineering task planning.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body suppressHydrationWarning>{children}</body>
    </html>
  );
}

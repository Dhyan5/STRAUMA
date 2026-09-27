import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "NHAA 14566 - Stress & Trauma Assessment (prototype)",
  description:
    "Prototype for demonstration purposes. Not a diagnostic tool. All risk flags are reviewed by trained personnel.",
  robots: { index: false, follow: false },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}

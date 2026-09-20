import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI BI Assistant · Analytics Workspace",
  description: "Conversational Analytics powered by Superset",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="vi">
      <body>{children}</body>
    </html>
  );
}

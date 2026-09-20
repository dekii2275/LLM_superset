import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI BI Assistant",
  description: "Natural Language Analytics powered by Superset",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}

import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI BI Assistant · Không gian làm việc phân tích",
  description: "Phân tích hội thoại trên nền tảng Superset",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="vi">
      <body>{children}</body>
    </html>
  );
}

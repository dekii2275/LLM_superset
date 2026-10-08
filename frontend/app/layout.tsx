import type { Metadata } from "next";
import { DatasetProvider } from "@/context/DatasetContext";
import { AuthProvider } from "@/context/AuthContext";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI BI Assistant · Không gian làm việc phân tích",
  description: "Phân tích hội thoại trên nền tảng Superset",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="vi">
      <body>
        <AuthProvider>
          <DatasetProvider>{children}</DatasetProvider>
        </AuthProvider>
      </body>
    </html>
  );
}

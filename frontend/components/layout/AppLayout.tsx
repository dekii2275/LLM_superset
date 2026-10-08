"use client";

import { useState } from "react";
import { AppHeader } from "@/components/layout/AppHeader";
import { Sidebar } from "@/components/layout/Sidebar";
import { useAuth } from "@/context/AuthContext";
import { LoginScreen } from "@/components/auth/LoginScreen";
import type { ChatSession, DatasetSummary } from "@/lib/types";

type AppLayoutProps = {
  children: React.ReactNode;
  onNewAnalysis?: () => void;
  singleColumn?: boolean;
  activeDatasetId?: number | null;
  onSelectDataset?: (id: number, dataset?: DatasetSummary) => void;
  sessions?: ChatSession[];
  activeSessionId?: string | null;
  onSelectSession?: (id: string) => void;
  onDeleteSession?: (id: string) => void;
};

export function AppLayout({
  children,
  onNewAnalysis,
  singleColumn = false,
  activeDatasetId,
  onSelectDataset,
  sessions,
  activeSessionId,
  onSelectSession,
  onDeleteSession,
}: AppLayoutProps) {
  const { user, loading: authLoading } = useAuth();
  const [sidebarOpen, setSidebarOpen] = useState(false);

  // Màn hình chờ khởi tạo
  if (authLoading) {
    return (
      <div
        className="login-screen-wrap"
        style={{ color: "#FFFFFF", flexDirection: "column", gap: "12px" }}
      >
        <div style={{ fontSize: "32px", animation: "spin 1s linear infinite" }}>⚡</div>
        <p style={{ fontSize: "14px", fontWeight: 600, color: "#94A3B8" }}>
          Đang nạp hệ thống phân tích...
        </p>
      </div>
    );
  }

  // Cổng bảo vệ: Bắt buộc bấm đăng nhập xong thì mới nạp toàn bộ không gian web
  if (!user) {
    return <LoginScreen />;
  }

  return (
    <div className={`app-frame ${sidebarOpen ? "sidebar-open" : ""}`}>
      <AppHeader
        sidebarOpen={sidebarOpen}
        onToggleSidebar={() => setSidebarOpen((open) => !open)}
        activeDatasetId={activeDatasetId}
        onSelectDataset={onSelectDataset}
      />
      <main className={`workspace ${singleColumn ? "single-column" : ""}`} id="main">
        <Sidebar
          onNewAnalysis={onNewAnalysis}
          sessions={sessions}
          activeSessionId={activeSessionId}
          onSelectSession={onSelectSession}
          onDeleteSession={onDeleteSession}
        />
        {sidebarOpen && (
          <button
            className="mobile-sidebar-scrim"
            type="button"
            aria-label="Đóng điều hướng"
            onClick={() => setSidebarOpen(false)}
          />
        )}
        {children}
      </main>
    </div>
  );
}

"use client";

import { useState } from "react";
import { AppHeader } from "@/components/layout/AppHeader";
import { Sidebar } from "@/components/layout/Sidebar";

type AppLayoutProps = {
  children: React.ReactNode;
  onNewAnalysis?: () => void;
  singleColumn?: boolean;
};

export function AppLayout({ children, onNewAnalysis, singleColumn = false }: AppLayoutProps) {
  const [sidebarOpen, setSidebarOpen] = useState(false);

  return (
    <div className={`app-frame ${sidebarOpen ? "sidebar-open" : ""}`}>
      <AppHeader
        sidebarOpen={sidebarOpen}
        onToggleSidebar={() => setSidebarOpen((open) => !open)}
      />
      <main className={`workspace ${singleColumn ? "single-column" : ""}`} id="main">
        <Sidebar onNewAnalysis={onNewAnalysis} />
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

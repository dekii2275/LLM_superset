"use client";

import { useRouter } from "next/navigation";
import { AppLayout } from "@/components/layout/AppLayout";
import { EmbeddedDashboard } from "@/components/superset/EmbeddedDashboard";
import { useDataset } from "@/context/DatasetContext";

export default function DashboardPage() {
  const router = useRouter();
  const { activeDataset, activeDatasetId, setActiveDatasetId } = useDataset();

  const hasDashboard = Boolean(activeDataset?.default_dashboard_id);
  const dashboardId = activeDataset?.default_dashboard_id ?? undefined;
  const dashboardTitle = activeDataset?.default_dashboard_title ?? activeDataset?.name ?? undefined;

  return (
    <AppLayout singleColumn activeDatasetId={activeDatasetId} onSelectDataset={setActiveDatasetId}>
      <section className="route-page dashboard-route" aria-label="Bảng điều khiển">
        {activeDataset && !hasDashboard ? (
          <div className="dashboard-disabled-card">
            <div className="disabled-icon-wrap">
              <span style={{ fontSize: 28 }}>📊</span>
            </div>
            <h2>Bảng điều khiển chưa được kích hoạt</h2>
            <p>
              Bộ dữ liệu <strong>{activeDataset.name || activeDataset.table_name}</strong> hiện đang
              tắt hiển thị nhúng hoặc chưa được liên kết với Dashboard nào trong Superset.
            </p>
            <button
              type="button"
              className="action-button-primary"
              onClick={() => router.push("/datasets")}
            >
              <span>Mở Quản lý dữ liệu để cấu hình</span>
            </button>
          </div>
        ) : (
          <EmbeddedDashboard
            key={dashboardId || "default"}
            dashboardId={dashboardId}
            title={dashboardTitle}
            onClose={() => router.push("/")}
          />
        )}
      </section>
    </AppLayout>
  );
}

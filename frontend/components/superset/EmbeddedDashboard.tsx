"use client";

import { useEffect, useRef, useState } from "react";
import { embedDashboard } from "@superset-ui/embedded-sdk";
import { apiUrl, getSupersetCharts } from "@/lib/api";
import { Icon } from "@/components/ui/Icon";
import { ChartExplanationModal } from "./ChartExplanationModal";
import type { SupersetChartItem } from "@/lib/types";

type EmbedConfig = {
  dashboard_id: string;
  superset_url: string;
};

type EmbeddedDashboardProps = {
  onClose?: () => void;
  dashboardId?: number;
  title?: string;
  variant?: "page" | "inline";
};

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(apiUrl(path), { cache: "no-store" });
  if (!response.ok) {
    const detail = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(detail?.detail ?? "Không thể kết nối với Superset.");
  }
  return response.json() as Promise<T>;
}

export function EmbeddedDashboard({ onClose, dashboardId, title, variant = "page" }: EmbeddedDashboardProps) {
  const mountPoint = useRef<HTMLDivElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);

  const [charts, setCharts] = useState<SupersetChartItem[]>([]);
  const [loadingCharts, setLoadingCharts] = useState(false);
  const [showChartDropdown, setShowChartDropdown] = useState(false);
  const [chartSearch, setChartSearch] = useState("");
  const [selectedChart, setSelectedChart] = useState<SupersetChartItem | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function mountDashboard() {
      try {
        const resource = dashboardId ? `/api/v1/superset/dashboard/${dashboardId}` : "/api/v1/superset";
        const config = await getJson<EmbedConfig>(`${resource}/embed-config`);
        if (cancelled || !mountPoint.current) return;

        await embedDashboard({
          id: config.dashboard_id,
          supersetDomain: config.superset_url,
          mountPoint: mountPoint.current,
          fetchGuestToken: async () => {
            const token = await getJson<{ token: string }>(`${resource}/guest-token`);
            return token.token;
          },
          dashboardUiConfig: {
            hideTitle: true,
            hideTab: false,
            hideChartControls: true,
            filters: { expanded: true },
          },
        });
      } catch (embedError) {
        if (!cancelled) {
          setError(embedError instanceof Error ? embedError.message : "Không thể tải Superset.");
        }
      }
    }

    void mountDashboard();
    return () => {
      cancelled = true;
      mountPoint.current?.replaceChildren();
    };
  }, [dashboardId]);

  useEffect(() => {
    let active = true;
    setLoadingCharts(true);
    getSupersetCharts(dashboardId)
      .then((items) => {
        if (active) setCharts(items);
      })
      .catch(() => {
        // Fallback gracefully without breaking embed
      })
      .finally(() => {
        if (active) setLoadingCharts(false);
      });

    return () => {
      active = false;
    };
  }, [dashboardId]);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setShowChartDropdown(false);
      }
    };
    if (showChartDropdown) {
      document.addEventListener("mousedown", handleClickOutside);
    }
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, [showChartDropdown]);

  const filteredCharts = charts.filter((c) =>
    c.slice_name.toLowerCase().includes(chartSearch.toLowerCase()),
  );

  // Top highlight charts for quick pills (prefer non-kpi charts like pie, bar, line)
  const quickPillCharts = charts
    .filter((c) => c.viz_type !== "kpi")
    .slice(0, 4);

  return (
    <>
      <section
        className={`superset-embed ${variant === "inline" ? "superset-embed-inline" : ""}`}
        role={variant === "inline" ? undefined : "dialog"}
        aria-modal={variant === "inline" ? undefined : true}
        aria-label="Bảng điều khiển Superset được nhúng"
      >
        <div className="superset-embed-header">
          <div className="superset-header-title-group">
            <p className="panel-eyebrow">BẢNG ĐIỀU KHIỂN TRỰC TIẾP</p>
            <h2>{title ?? "Phân tích chuyến đi Taxi NYC"}</h2>
          </div>

          <div className="superset-header-actions" ref={dropdownRef}>
            <div className="superset-charts-menu-wrap">
              <button
                type="button"
                className="superset-explain-trigger"
                onClick={() => setShowChartDropdown((prev) => !prev)}
                aria-expanded={showChartDropdown}
                title="Nhấn để chọn và xem giải thích của AI cho bất kỳ biểu đồ nào"
              >
                <Icon name="sparkle" size={16} />
                <span>✦ AI Giải thích biểu đồ có sẵn</span>
                <span className="superset-badge-count">
                  {loadingCharts ? "…" : charts.length}
                </span>
              </button>

              {showChartDropdown && (
                <div className="superset-charts-dropdown" role="dialog" aria-label="Danh sách biểu đồ giải thích">
                  <div className="superset-dropdown-top">
                    <strong>Chọn biểu đồ cần AI giải thích</strong>
                    <p>Hệ thống sẽ lấy dữ liệu thực tế và phân tích xu hướng</p>
                    <input
                      type="search"
                      placeholder="Tìm biểu đồ theo tên…"
                      value={chartSearch}
                      onChange={(e) => setChartSearch(e.target.value)}
                      className="superset-search-input"
                      autoFocus
                    />
                  </div>

                  <div className="superset-dropdown-list">
                    {loadingCharts ? (
                      <p className="superset-dropdown-empty">Đang tải danh sách biểu đồ từ Superset…</p>
                    ) : filteredCharts.length === 0 ? (
                      <p className="superset-dropdown-empty">
                        {charts.length === 0
                          ? "Đang kết nối tải biểu đồ…"
                          : "Không tìm thấy biểu đồ phù hợp"}
                      </p>
                    ) : (
                      filteredCharts.map((item) => (
                        <button
                          key={item.id}
                          type="button"
                          className="superset-dropdown-item"
                          onClick={() => {
                            setSelectedChart(item);
                            setShowChartDropdown(false);
                          }}
                        >
                          <span className="superset-dropdown-item-icon">
                            {item.viz_type === "pie"
                              ? "🥧"
                              : item.viz_type === "line"
                              ? "📈"
                              : item.viz_type === "kpi"
                              ? "🎯"
                              : "📊"}
                          </span>
                          <div className="superset-dropdown-item-info">
                            <span className="superset-dropdown-item-title">{item.slice_name}</span>
                            <span className="superset-dropdown-item-type">
                              {item.viz_type === "kpi"
                                ? "Chỉ số tổng hợp"
                                : item.viz_type === "pie"
                                ? "Biểu đồ tròn"
                                : item.viz_type === "line"
                                ? "Biểu đồ đường"
                                : "Biểu đồ cột"}
                            </span>
                          </div>
                          <span className="superset-dropdown-item-arrow">Giải thích ✦</span>
                        </button>
                      ))
                    )}
                  </div>
                </div>
              )}
            </div>

            <button type="button" className="superset-close" onClick={onClose}>
              Quay lại phân tích
            </button>
          </div>
        </div>

        {quickPillCharts.length > 0 && (
          <div className="superset-quick-bar" aria-label="Các biểu đồ gợi ý giải thích">
            <span className="superset-quick-label">
              <Icon name="sparkle" size={14} /> Giải thích nhanh:
            </span>
            <div className="superset-quick-chips">
              {quickPillCharts.map((c) => (
                <button
                  key={c.id}
                  type="button"
                  className="superset-quick-chip"
                  onClick={() => setSelectedChart(c)}
                >
                  <span>
                    {c.viz_type === "pie" ? "🥧" : c.viz_type === "line" ? "📈" : "📊"}
                  </span>
                  <span className="superset-chip-text">{c.slice_name}</span>
                </button>
              ))}
            </div>
          </div>
        )}

        {error ? (
          <p className="superset-embed-error">{error}</p>
        ) : (
          <div ref={mountPoint} className="superset-embed-frame" />
        )}
      </section>

      {/* Pop-up Modal hiển thị giải thích của AI */}
      <ChartExplanationModal
        chart={selectedChart}
        onClose={() => setSelectedChart(null)}
      />
    </>
  );
}


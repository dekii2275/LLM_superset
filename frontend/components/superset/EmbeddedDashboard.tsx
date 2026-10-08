"use client";

import { useEffect, useRef, useState } from "react";
import {
  embedDashboard,
  type EmbeddedDashboard as SupersetEmbeddedDashboard,
} from "@superset-ui/embedded-sdk";
import { apiUrl, getSupersetCharts } from "@/lib/api";
import { Icon } from "@/components/ui/Icon";
import { ChartExplanationModal } from "./ChartExplanationModal";
import type { SupersetChartItem } from "@/lib/types";
import type { DashboardReport } from "@/lib/docxReport";

type EmbedConfig = {
  dashboard_id: string;
  superset_url: string;
};

type ReportFileHandle = {
  createWritable(): Promise<{
    write(data: Blob): Promise<void>;
    close(): Promise<void>;
  }>;
};

type SavePickerWindow = Window & {
  showSaveFilePicker?: (options: {
    suggestedName: string;
    types: { description: string; accept: Record<string, string[]> }[];
  }) => Promise<ReportFileHandle>;
};

type EmbeddedDashboardProps = {
  onClose?: () => void;
  dashboardId?: number;
  title?: string;
  variant?: "page" | "inline";
};

async function getJson<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(apiUrl(path), { cache: "no-store", ...options });
  if (!response.ok) {
    const detail = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(detail?.detail ?? "Không thể kết nối với Superset.");
  }
  return response.json() as Promise<T>;
}

async function createPdf(element: HTMLElement): Promise<Blob> {
  const [{ default: html2canvas }, { jsPDF }] = await Promise.all([
    import("html2canvas"),
    import("jspdf"),
  ]);
  const canvas = await html2canvas(element, {
    backgroundColor: "#fff",
    scale: 2,
    useCORS: true,
    onclone: (documentClone) => {
      const reportClone = documentClone.querySelector<HTMLElement>(".dashboard-report");
      if (reportClone) {
        Object.assign(reportClone.style, {
          position: "fixed",
          top: "0",
          left: "0",
          width: "794px",
          maxWidth: "none",
          margin: "0",
          visibility: "visible",
          opacity: "1",
        });
      }
    },
  });
  const pdf = new jsPDF({ unit: "pt", format: "a4", compress: true });
  const margin = 36;
  const contentWidth = pdf.internal.pageSize.getWidth() - margin * 2;
  const contentHeight = pdf.internal.pageSize.getHeight() - margin * 2;
  const sourcePageHeight = Math.floor((canvas.width * contentHeight) / contentWidth);

  for (let top = 0; top < canvas.height; top += sourcePageHeight) {
    if (top > 0) pdf.addPage();
    const slice = document.createElement("canvas");
    slice.width = canvas.width;
    slice.height = Math.min(sourcePageHeight, canvas.height - top);
    slice
      .getContext("2d")
      ?.drawImage(canvas, 0, top, canvas.width, slice.height, 0, 0, canvas.width, slice.height);
    pdf.addImage(
      slice.toDataURL("image/jpeg", 0.94),
      "JPEG",
      margin,
      margin,
      contentWidth,
      (slice.height * contentWidth) / canvas.width,
    );
  }

  return pdf.output("blob");
}

async function waitForReportCharts(element: HTMLElement): Promise<void> {
  const images = Array.from(element.querySelectorAll<HTMLImageElement>(".dashboard-report-image"));
  await Promise.all(
    images.map(async (image) => {
      try {
        await image.decode();
      } catch {
        throw new Error(`Không thể tải biểu đồ “${image.alt}” để xuất PDF.`);
      }
    }),
  );
}

function downloadReport(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function EmbeddedDashboard({
  onClose,
  dashboardId,
  title,
  variant = "page",
}: EmbeddedDashboardProps) {
  const mountPoint = useRef<HTMLDivElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const dashboardClient = useRef<SupersetEmbeddedDashboard | null>(null);
  const reportElement = useRef<HTMLElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [report, setReport] = useState<DashboardReport | null>(null);
  const [reportError, setReportError] = useState<string | null>(null);
  const [reportStatus, setReportStatus] = useState<string | null>(null);
  const [reportLoading, setReportLoading] = useState(false);
  const [reportFormat, setReportFormat] = useState<"pdf" | "docx">("pdf");

  async function createReport(format: "pdf" | "docx") {
    setReport(null);
    setReportError(null);
    setReportFormat(format);
    const fileType =
      format === "pdf"
        ? { label: "PDF", mime: "application/pdf", extension: ".pdf" }
        : {
            label: "DOCX",
            mime: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            extension: ".docx",
          };
    const filename = `Bao-cao-dashboard${fileType.extension}`;
    setReportStatus(`Chọn nơi lưu báo cáo ${fileType.label}…`);
    setReportLoading(true);
    try {
      const saveWindow = window as SavePickerWindow;
      let fileHandle: ReportFileHandle | null = null;
      if (saveWindow.showSaveFilePicker) {
        try {
          fileHandle = await saveWindow.showSaveFilePicker({
            suggestedName: filename,
            types: [
              {
                description: `Tài liệu ${fileType.label}`,
                accept: { [fileType.mime]: [fileType.extension] },
              },
            ],
          });
        } catch (pickerError) {
          if (pickerError instanceof DOMException && pickerError.name === "AbortError") {
            setReportStatus(null);
            return;
          }
          throw pickerError;
        }
      }

      setReportStatus(`Đang lấy dữ liệu và tạo báo cáo ${fileType.label}…`);
      const embedded = dashboardClient.current;
      if (!embedded) throw new Error("Dashboard chưa tải xong để tạo báo cáo.");
      const [activeTabs, dataMask] = await Promise.all([
        embedded.getActiveTabs(),
        embedded.getDataMask(),
      ]);
      const reportData = await getJson<DashboardReport>("/api/v1/superset/report", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ active_tabs: activeTabs, data_mask: dataMask }),
      });
      setReport(reportData);
      let reportBlob: Blob;
      if (format === "pdf") {
        await new Promise<void>((resolve) =>
          requestAnimationFrame(() => requestAnimationFrame(() => resolve())),
        );
        if (!reportElement.current) throw new Error("Không tìm thấy nội dung báo cáo để xuất PDF.");
        const reportNode = reportElement.current;
        reportNode.style.left = "0px";
        reportNode.style.visibility = "visible";
        reportNode.style.opacity = "0";
        try {
          await waitForReportCharts(reportNode);
          reportBlob = await createPdf(reportNode);
        } finally {
          reportNode.style.left = "";
          reportNode.style.visibility = "";
          reportNode.style.opacity = "";
        }
      } else {
        const { createDocxReport } = await import("@/lib/docxReport");
        reportBlob = await createDocxReport(reportData);
      }

      if (fileHandle) {
        const writable = await fileHandle.createWritable();
        await writable.write(reportBlob);
        await writable.close();
        setReportStatus(`Đã lưu báo cáo ${fileType.label}.`);
      } else {
        downloadReport(reportBlob, filename);
        setReportStatus(`Đã tải báo cáo ${fileType.label} về máy.`);
      }
    } catch (reportError) {
      setReportStatus(null);
      setReportError(reportError instanceof Error ? reportError.message : "Không thể tạo báo cáo.");
    } finally {
      setReportLoading(false);
    }
  }

  const [charts, setCharts] = useState<SupersetChartItem[]>([]);
  const [loadingCharts, setLoadingCharts] = useState(false);
  const [showChartDropdown, setShowChartDropdown] = useState(false);
  const [chartSearch, setChartSearch] = useState("");
  const [selectedChart, setSelectedChart] = useState<SupersetChartItem | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function mountDashboard() {
      try {
        const resource = dashboardId
          ? `/api/v1/superset/dashboard/${dashboardId}`
          : "/api/v1/superset";
        const config = await getJson<EmbedConfig>(`${resource}/embed-config`);
        if (cancelled || !mountPoint.current) return;

        const client = await embedDashboard({
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
        if (cancelled) client.unmount();
        else dashboardClient.current = client;
      } catch (embedError) {
        if (!cancelled) {
          setError(embedError instanceof Error ? embedError.message : "Không thể tải Superset.");
        }
      }
    }

    void mountDashboard();
    return () => {
      cancelled = true;
      dashboardClient.current?.unmount();
      dashboardClient.current = null;
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
  const quickPillCharts = charts.filter((c) => c.viz_type !== "kpi").slice(0, 4);

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
                <span className="superset-badge-count">{loadingCharts ? "…" : charts.length}</span>
              </button>

              {showChartDropdown && (
                <div
                  className="superset-charts-dropdown"
                  role="dialog"
                  aria-label="Danh sách biểu đồ giải thích"
                >
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
                      <p className="superset-dropdown-empty">
                        Đang tải danh sách biểu đồ từ Superset…
                      </p>
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

            <details
              className="superset-report-menu"
              onClick={(event) => {
                if (reportLoading) event.preventDefault();
              }}
            >
              <summary className="superset-report-button" aria-disabled={reportLoading}>
                {reportLoading ? `Đang tạo báo cáo ${reportFormat.toUpperCase()}…` : "Tạo báo cáo"}
              </summary>
              <div className="superset-report-options">
                <button
                  type="button"
                  onClick={(event) => {
                    event.currentTarget.closest("details")!.open = false;
                    void createReport("pdf");
                  }}
                  disabled={reportLoading}
                >
                  PDF (.pdf)
                </button>
                <button
                  type="button"
                  onClick={(event) => {
                    event.currentTarget.closest("details")!.open = false;
                    void createReport("docx");
                  }}
                  disabled={reportLoading}
                >
                  DOCX (.docx)
                </button>
              </div>
            </details>

            <button type="button" className="superset-close" onClick={onClose}>
              Quay lại phân tích
            </button>
          </div>
        </div>
        {reportError && (
          <p className="superset-embed-error" role="alert">
            {reportError}
          </p>
        )}
        {(reportLoading || reportStatus) && (
          <p className="superset-report-status" role="status">
            {reportStatus}
          </p>
        )}

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
                  <span>{c.viz_type === "pie" ? "🥧" : c.viz_type === "line" ? "📈" : "📊"}</span>
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

        {report && (
          <article ref={reportElement} className="dashboard-report" aria-label="Báo cáo dashboard">
            <h1>{report.dashboard_title}</h1>
            <h2>Báo cáo phân tích dashboard</h2>
            <p className="dashboard-report-meta">
              Tạo lúc {new Date(report.generated_at).toLocaleString("vi-VN")}
            </p>
            <p className="dashboard-report-note">
              Tab: {report.active_tab_title || "Dashboard"}
              <br />
              {report.applied_filters.length > 0
                ? `Bộ lọc đang chọn: ${report.applied_filters.join("; ")}`
                : "Không có bộ lọc đang chọn."}
            </p>
            <section className="dashboard-report-overview">
              <h3>Tổng quan</h3>
              <p>{report.analysis.overview}</p>
              {report.analysis.highlights.length > 0 && (
                <ul>
                  {report.analysis.highlights.map((highlight, index) => (
                    <li key={index}>{highlight}</li>
                  ))}
                </ul>
              )}
            </section>
            {report.charts.map((chart) => {
              const insight = report.analysis.chart_insights.find(
                (item) => item.chart_id === chart.id,
              );
              return (
                <section className="dashboard-report-chart-section" key={chart.id}>
                  <h3>{chart.title}</h3>
                  <p>{insight?.insight ?? "Chưa có nhận xét riêng cho biểu đồ này."}</p>
                  {chart.screenshot_base64 && (
                    <img
                      className="dashboard-report-image"
                      src={`data:image/png;base64,${chart.screenshot_base64}`}
                      alt={`Biểu đồ: ${chart.title}`}
                    />
                  )}
                  {chart.unavailable && <p>Không lấy được dữ liệu biểu đồ.</p>}
                  {chart.truncated && (
                    <p className="dashboard-report-chart-note">
                      Biểu đồ hiển thị {chart.rows.length} dòng mẫu trên tổng số {chart.row_count}{" "}
                      dòng.
                    </p>
                  )}
                </section>
              );
            })}
          </article>
        )}
      </section>

      {/* Pop-up Modal hiển thị giải thích của AI */}
      <ChartExplanationModal chart={selectedChart} onClose={() => setSelectedChart(null)} />
    </>
  );
}

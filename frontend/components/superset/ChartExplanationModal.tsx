"use client";

import { useEffect, useState } from "react";
import { Icon } from "@/components/ui/Icon";
import { explainSupersetChart } from "@/lib/api";
import type { SupersetChartExplanationResponse, SupersetChartItem } from "@/lib/types";

type ChartExplanationModalProps = {
  chart: SupersetChartItem | null;
  onClose: () => void;
};

function chartTypeBadge(vizType: string): { label: string; icon: string } {
  switch (vizType) {
    case "pie":
      return { label: "Biểu đồ tròn", icon: "🥧" };
    case "line":
      return { label: "Biểu đồ đường", icon: "📈" };
    case "bar":
      return { label: "Biểu đồ cột", icon: "📊" };
    case "area":
      return { label: "Biểu đồ vùng", icon: "📉" };
    case "kpi":
      return { label: "Chỉ số tổng hợp", icon: "🎯" };
    default:
      return { label: "Biểu đồ", icon: "📊" };
  }
}

export function ChartExplanationModal({ chart, onClose }: ChartExplanationModalProps) {
  const [data, setData] = useState<SupersetChartExplanationResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showSql, setShowSql] = useState(false);

  useEffect(() => {
    if (!chart) {
      setData(null);
      setError(null);
      return;
    }

    let active = true;
    setLoading(true);
    setError(null);
    setData(null);
    setShowSql(false);

    explainSupersetChart(chart.id)
      .then((res) => {
        if (active) setData(res);
      })
      .catch((err) => {
        if (active) {
          setError(
            err instanceof Error ? err.message : "Không thể tải giải thích biểu đồ từ Superset.",
          );
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, [chart]);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  if (!chart) return null;

  const badge = chartTypeBadge(data?.viz_type || chart.viz_type);

  return (
    <div className="chart-modal-backdrop" onClick={onClose} role="presentation">
      <div
        className="chart-modal-window"
        role="dialog"
        aria-modal="true"
        aria-labelledby="chart-modal-title"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="chart-modal-header">
          <div className="chart-modal-header-left">
            <div className="chart-modal-badges">
              <span className="chart-modal-badge">
                <span aria-hidden="true">{badge.icon}</span> {badge.label}
              </span>
              <span className="chart-modal-gemini-badge">
                <Icon name="sparkle" size={12} /> Gemini AI
              </span>
            </div>
            <h3 id="chart-modal-title">{chart.slice_name}</h3>
          </div>
          <button
            type="button"
            className="chart-modal-close"
            onClick={onClose}
            aria-label="Đóng cửa sổ giải thích"
          >
            <Icon name="close" size={18} />
          </button>
        </header>

        <div className="chart-modal-body">
          {loading && (
            <div className="chart-modal-loading" aria-live="polite">
              <div className="chart-modal-spinner" aria-hidden="true" />
              <div>
                <strong>Gemini đang phân tích biểu đồ…</strong>
                <p>Đang đọc số liệu thực từ Superset và tổng hợp nhận định kinh doanh</p>
              </div>
            </div>
          )}

          {error && (
            <div className="chart-modal-error" role="alert">
              <p>
                <strong>Không thể phân tích:</strong> {error}
              </p>
              <button
                type="button"
                className="chart-modal-retry"
                onClick={() => {
                  setLoading(true);
                  setError(null);
                  explainSupersetChart(chart.id)
                    .then(setData)
                    .catch((err) =>
                      setError(err instanceof Error ? err.message : "Lỗi không xác định"),
                    )
                    .finally(() => setLoading(false));
                }}
              >
                Thử lại
              </button>
            </div>
          )}

          {data && (
            <div className="chart-modal-content" aria-live="polite">
              <section className="chart-modal-card chart-modal-summary">
                <div className="chart-modal-card-title">
                  <Icon name="sparkle" size={17} />
                  <h4>Tóm tắt phân tích</h4>
                </div>
                <p>{data.explanation.summary}</p>
              </section>

              {data.explanation.highlights && data.explanation.highlights.length > 0 && (
                <section className="chart-modal-card chart-modal-highlights">
                  <div className="chart-modal-card-title">
                    <span className="chart-modal-indicator" aria-hidden="true">
                      ✦
                    </span>
                    <h4>Điểm nổi bật &amp; Xu hướng</h4>
                  </div>
                  <ul>
                    {data.explanation.highlights.map((point, index) => (
                      <li key={index}>{point}</li>
                    ))}
                  </ul>
                </section>
              )}

              <section className="chart-modal-card chart-modal-note">
                <div className="chart-modal-card-title">
                  <span className="chart-modal-note-icon" aria-hidden="true">
                    ℹ
                  </span>
                  <h4>Lưu ý phạm vi dữ liệu</h4>
                </div>
                <p>{data.explanation.note}</p>
              </section>

              {data.sql && (
                <section className="chart-modal-sql-section">
                  <button
                    type="button"
                    className="chart-modal-sql-toggle"
                    onClick={() => setShowSql((prev) => !prev)}
                    aria-expanded={showSql}
                  >
                    <Icon name="code" size={15} />
                    <span>
                      {showSql ? "Ẩn câu lệnh SQL truy vấn" : "Xem câu lệnh SQL truy vấn"}
                    </span>
                  </button>
                  {showSql && (
                    <pre className="chart-modal-sql-code">
                      <code>{data.sql}</code>
                    </pre>
                  )}
                </section>
              )}
            </div>
          )}
        </div>

        <footer className="chart-modal-footer">
          <button type="button" className="chart-modal-btn-close" onClick={onClose}>
            Đóng
          </button>
        </footer>
      </div>
    </div>
  );
}

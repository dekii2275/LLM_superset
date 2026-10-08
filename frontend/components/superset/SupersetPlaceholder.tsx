"use client";

import Image from "next/image";
import Link from "next/link";
import { Icon } from "@/components/ui/Icon";
import type { DatasetSummary } from "@/lib/types";

type SupersetPlaceholderProps = {
  dataset?: DatasetSummary | null;
  onQuickAsk?: (question: string) => void;
};

export function SupersetPlaceholder({ dataset, onQuickAsk }: SupersetPlaceholderProps) {
  const suggestions = dataset
    ? [
        `Phân tích tóm tắt các cột và chỉ số trong bảng ${dataset.name}`,
        `Xem 10 dòng đầu tiên của bảng raw.${dataset.table_name}`,
        `Gợi ý biểu đồ phân tích phù hợp cho dữ liệu này`,
      ]
    : ["Tổng quan về các nguồn dữ liệu hiện có", "Hướng dẫn kết nối và phân tích dữ liệu Superset"];

  return (
    <div className="superset-placeholder" aria-label="Superset Dashboard Placeholder">
      <div className="superset-placeholder-banner">
        <div className="superset-placeholder-bg-pattern" />

        <div className="superset-placeholder-hero">
          <div className="superset-logo-box">
            <Image
              src="/superset-logo-transparent.png"
              alt="Apache Superset"
              width={160}
              height={94}
              priority
            />
          </div>

          <div className="superset-placeholder-content">
            <div className="superset-badge-status">
              <span className="badge-dot" style={{ background: dataset ? "#f59e0b" : "#64748b" }} />
              <span>
                {dataset ? "Chưa có Bảng điều khiển (Dashboard)" : "Apache Superset BI Platform"}
              </span>
            </div>

            <h2 className="superset-placeholder-title">
              {dataset ? (
                <>
                  Bộ dữ liệu: <span className="highlight-dataset">{dataset.name}</span>
                </>
              ) : (
                "Chưa chọn nguồn dữ liệu phân tích"
              )}
            </h2>

            <p className="superset-placeholder-desc">
              {dataset ? (
                <>
                  Bảng SQL: <code>raw.{dataset.table_name}</code> ({dataset.column_count} cột
                  {dataset.metric_count > 0 ? `, ${dataset.metric_count} metrics` : ""}). Hiện chưa
                  có bảng điều khiển nào được liên kết với bộ dữ liệu này. Bạn có thể yêu cầu AI tự
                  động tạo bảng điều khiển hoặc gán bảng điều khiển trong Quản lý dữ liệu.
                </>
              ) : (
                "Vui lòng chọn một nguồn dữ liệu ở thanh điều hướng phía trên để bắt đầu phân tích."
              )}
            </p>

            <div
              className="superset-placeholder-actions"
              style={{ display: "flex", gap: "10px", flexWrap: "wrap", marginTop: "16px" }}
            >
              {dataset && onQuickAsk && (
                <button
                  type="button"
                  className="btn-action-emerald"
                  style={{ background: "#0E4A86", borderColor: "#0E4A86", cursor: "pointer" }}
                  onClick={() =>
                    onQuickAsk(`Tạo bảng điều khiển tổng quan cho bộ dữ liệu ${dataset.name}`)
                  }
                >
                  <Icon name="sparkle" size={14} />
                  <span>Yêu cầu AI tạo Bảng điều khiển</span>
                </button>
              )}
              <Link href="/datasets" className="btn-action-emerald">
                <Icon name="database" size={14} />
                <span>Quản lý dữ liệu & Gán Dashboard</span>
              </Link>
            </div>
          </div>
        </div>
      </div>

      {dataset && onQuickAsk && (
        <div className="superset-quick-suggestions">
          <p className="suggestions-label">
            <Icon name="sparkle" size={13} />
            <span>Gợi ý câu hỏi phân tích cho bộ dữ liệu này:</span>
          </p>
          <div className="suggestions-grid">
            {suggestions.map((prompt, idx) => (
              <button
                key={idx}
                type="button"
                className="suggestion-quick-btn"
                onClick={() => onQuickAsk(prompt)}
              >
                <span>{prompt}</span>
                <span className="arrow-icon">→</span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

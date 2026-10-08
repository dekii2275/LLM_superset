"use client";

import { useCallback, useEffect, useState } from "react";
import { Icon } from "@/components/ui/Icon";
import {
  addGlossaryTerm,
  addVerifiedMetric,
  deleteGlossaryTerm,
  deleteVerifiedMetric,
  getGlossary,
  getVerifiedMetrics,
} from "@/lib/api";
import type { BusinessGlossaryItem, DatasetSummary, VerifiedMetricItem } from "@/lib/types";

type SemanticLayerPanelProps = {
  datasets: DatasetSummary[];
  activeDatasetId: number | null;
};

export function SemanticLayerPanel({ datasets, activeDatasetId }: SemanticLayerPanelProps) {
  const [filterDatasetId, setFilterDatasetId] = useState<number | "all">(activeDatasetId ?? "all");
  const [glossary, setGlossary] = useState<BusinessGlossaryItem[]>([]);
  const [metrics, setMetrics] = useState<VerifiedMetricItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");

  // Modals
  const [showAddGlossary, setShowAddGlossary] = useState(false);
  const [showAddMetric, setShowAddMetric] = useState(false);

  // Form states
  const [glossaryTerm, setGlossaryTerm] = useState("");
  const [glossaryTargetType, setGlossaryTargetType] = useState<string>("column");
  const [glossaryTargetName, setGlossaryTargetName] = useState("");
  const [glossaryDesc, setGlossaryDesc] = useState("");
  const [glossaryDatasetId, setGlossaryDatasetId] = useState<number>(
    activeDatasetId ?? (datasets[0]?.id || 1),
  );

  const [metricDisplayName, setMetricDisplayName] = useState("");
  const [metricName, setMetricName] = useState("");
  const [metricSql, setMetricSql] = useState("");
  const [metricDesc, setMetricDesc] = useState("");
  const [metricDatasetId, setMetricDatasetId] = useState<number>(
    activeDatasetId ?? (datasets[0]?.id || 1),
  );

  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      const dsId = filterDatasetId === "all" ? undefined : filterDatasetId;
      const [gData, mData] = await Promise.all([getGlossary(dsId), getVerifiedMetrics(dsId)]);
      setGlossary(gData);
      setMetrics(mData);
    } catch {
      // Keep existing data on error
    } finally {
      setLoading(false);
    }
  }, [filterDatasetId]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  // Handle Add Glossary
  const handleAddGlossarySubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!glossaryTerm.trim() || !glossaryTargetName.trim()) {
      setFormError("Vui lòng điền đầy đủ thuật ngữ và tên trường ánh xạ.");
      return;
    }
    setSubmitting(true);
    setFormError(null);
    try {
      await addGlossaryTerm({
        dataset_id: glossaryDatasetId,
        term: glossaryTerm.trim(),
        target_type: glossaryTargetType,
        target_name: glossaryTargetName.trim(),
        description: glossaryDesc.trim() || undefined,
      });
      setShowAddGlossary(false);
      setGlossaryTerm("");
      setGlossaryTargetName("");
      setGlossaryDesc("");
      await loadData();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Thêm thuật ngữ thất bại.");
    } finally {
      setSubmitting(false);
    }
  };

  // Handle Add Metric
  const handleAddMetricSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!metricDisplayName.trim() || !metricName.trim() || !metricSql.trim()) {
      setFormError("Vui lòng điền đầy đủ tên hiển thị, mã định danh và biểu thức SQL.");
      return;
    }
    setSubmitting(true);
    setFormError(null);
    try {
      await addVerifiedMetric({
        dataset_id: metricDatasetId,
        display_name: metricDisplayName.trim(),
        metric_name: metricName.trim(),
        sql_expression: metricSql.trim(),
        description: metricDesc.trim() || undefined,
      });
      setShowAddMetric(false);
      setMetricDisplayName("");
      setMetricName("");
      setMetricSql("");
      setMetricDesc("");
      await loadData();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Thêm chỉ số thất bại.");
    } finally {
      setSubmitting(false);
    }
  };

  // Handle Delete
  const handleDeleteGlossary = async (id?: number) => {
    if (!id || !confirm("Bạn có chắc chắn muốn xóa thuật ngữ này khỏi từ điển?")) return;
    try {
      await deleteGlossaryTerm(id);
      await loadData();
    } catch {
      alert("Xóa thuật ngữ thất bại.");
    }
  };

  const handleDeleteMetric = async (id?: number) => {
    if (!id || !confirm("Bạn có chắc chắn muốn xóa chỉ số chuẩn này?")) return;
    try {
      await deleteVerifiedMetric(id);
      await loadData();
    } catch {
      alert("Xóa chỉ số thất bại.");
    }
  };

  // Filtered lists
  const filteredGlossary = glossary.filter((g) => {
    if (!search.trim()) return true;
    const q = search.toLowerCase();
    return (
      g.term.toLowerCase().includes(q) ||
      g.target_name.toLowerCase().includes(q) ||
      (g.description && g.description.toLowerCase().includes(q))
    );
  });

  const filteredMetrics = metrics.filter((m) => {
    if (!search.trim()) return true;
    const q = search.toLowerCase();
    return (
      m.display_name.toLowerCase().includes(q) ||
      m.metric_name.toLowerCase().includes(q) ||
      m.sql_expression.toLowerCase().includes(q) ||
      (m.description && m.description.toLowerCase().includes(q))
    );
  });

  const getDatasetLabel = (id: number) => {
    const ds = datasets.find((d) => d.id === id);
    return ds ? ds.name : `Dataset #${id}`;
  };

  return (
    <div className="semantic-panel">
      {/* Top Filter and Actions Bar */}
      <div className="semantic-toolbar">
        <div className="semantic-filter-group">
          <label htmlFor="datasetFilterSelect">
            <Icon name="database" size={15} />
            <span>Lọc theo bộ dữ liệu:</span>
          </label>
          <select
            id="datasetFilterSelect"
            className="semantic-select"
            value={filterDatasetId}
            onChange={(e) => {
              const val = e.target.value === "all" ? "all" : Number(e.target.value);
              setFilterDatasetId(val);
            }}
          >
            <option value="all">Tất cả bộ dữ liệu ({datasets.length})</option>
            {datasets.map((d) => (
              <option key={d.id} value={d.id}>
                {d.name} (#{d.id})
              </option>
            ))}
          </select>
        </div>

        <div className="semantic-search-box">
          <input
            type="text"
            placeholder="Tìm kiếm thuật ngữ hoặc công thức..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>

        <div className="semantic-action-buttons">
          <button
            type="button"
            className="action-button-primary sharp-btn"
            onClick={() => {
              setShowAddGlossary(true);
              setFormError(null);
            }}
          >
            <Icon name="plus" size={14} />
            <span>Thêm thuật ngữ</span>
          </button>
          <button
            type="button"
            className="action-button-primary sharp-btn emerald-btn"
            onClick={() => {
              setShowAddMetric(true);
              setFormError(null);
            }}
          >
            <Icon name="sparkle" size={14} />
            <span>Thêm chỉ số chuẩn</span>
          </button>
        </div>
      </div>

      {/* Semantic Summary Cards */}
      <div className="datasets-metrics-grid">
        <div className="datasets-metric-card">
          <div className="metric-top-row">
            <span className="metric-label">Từ điển nghiệp vụ</span>
            <span className="metric-icon-wrap purple">
              <Icon name="book" size={17} />
            </span>
          </div>
          <div className="metric-val">{glossary.length}</div>
          <div className="metric-hint">
            <span className="hint-dot purple" />
            <span>Đồng nghĩa & Quy tắc ngôn ngữ tự nhiên</span>
          </div>
        </div>

        <div className="datasets-metric-card">
          <div className="metric-top-row">
            <span className="metric-label">Chỉ số chuẩn (Golden SQL)</span>
            <span className="metric-icon-wrap emerald">
              <Icon name="chart" size={17} />
            </span>
          </div>
          <div className="metric-val">{metrics.length}</div>
          <div className="metric-hint">
            <span className="hint-dot emerald" />
            <span>Công thức tính toán được kiểm duyệt</span>
          </div>
        </div>

        <div className="datasets-metric-card">
          <div className="metric-top-row">
            <span className="metric-label">Phạm vi kích hoạt LLM</span>
            <span className="metric-icon-wrap blue">
              <Icon name="sparkle" size={17} />
            </span>
          </div>
          <div className="metric-val">
            {filterDatasetId === "all" ? "Tất cả" : getDatasetLabel(Number(filterDatasetId))}
          </div>
          <div className="metric-hint">
            <span className="hint-dot blue" />
            <span>Tự động tiêm vào prompt sinh SQL</span>
          </div>
        </div>
      </div>

      {/* Section 1: Business Glossary */}
      <section className="datasets-card semantic-section" aria-label="Từ điển nghiệp vụ">
        <div className="datasets-card-header">
          <div className="section-title-wrap">
            <h2>Từ điển nghiệp vụ (Business Glossary & Synonyms)</h2>
            <span className="badge-count">{filteredGlossary.length} thuật ngữ</span>
          </div>
          <p className="section-subtitle">
            Ánh xạ các từ lóng, viết tắt, ngôn ngữ kinh doanh (vd: &quot;doanh thu&quot;,
            &quot;khách&quot;, &quot;tip&quot;) sang cột hoặc bộ lọc SQL chính xác.
          </p>
        </div>

        {loading ? (
          <div className="datasets-loading">
            <span className="thinking-dots">
              <i />
              <i />
              <i />
            </span>
            <p>Đang tải từ điển nghiệp vụ…</p>
          </div>
        ) : filteredGlossary.length === 0 ? (
          <div className="datasets-empty">
            <Icon name="book" size={32} />
            <p>Chưa có thuật ngữ nghiệp vụ nào được định nghĩa cho bộ dữ liệu này.</p>
            <button
              type="button"
              className="action-button-primary sharp-btn"
              onClick={() => setShowAddGlossary(true)}
            >
              Thêm thuật ngữ đầu tiên
            </button>
          </div>
        ) : (
          <div className="datasets-table-wrap">
            <table className="datasets-table sharp-table">
              <thead>
                <tr>
                  <th style={{ width: "20%" }}>Thuật ngữ (Term)</th>
                  <th style={{ width: "15%" }}>Loại ánh xạ</th>
                  <th style={{ width: "22%" }}>Cột / Metric đích</th>
                  <th style={{ width: "23%" }}>Diễn giải nghiệp vụ</th>
                  <th style={{ width: "12%" }}>Dataset</th>
                  <th style={{ width: "8%", textAlign: "right" }}>Xóa</th>
                </tr>
              </thead>
              <tbody>
                {filteredGlossary.map((item) => (
                  <tr key={item.id ?? item.term}>
                    <td>
                      <strong className="term-text">&quot;{item.term}&quot;</strong>
                    </td>
                    <td>
                      <span className={`target-type-badge ${item.target_type}`}>
                        {item.target_type === "column"
                          ? "Cột dữ liệu"
                          : item.target_type === "metric"
                            ? "Chỉ số"
                            : "Bộ lọc"}
                      </span>
                    </td>
                    <td>
                      <code className="code-badge">{item.target_name}</code>
                    </td>
                    <td className="desc-cell">
                      {item.description || <span className="text-muted">—</span>}
                    </td>
                    <td>
                      <span className="dataset-tag">{getDatasetLabel(item.dataset_id)}</span>
                    </td>
                    <td style={{ textAlign: "right" }}>
                      <button
                        type="button"
                        className="btn-danger-icon"
                        title="Xóa thuật ngữ này"
                        onClick={() => handleDeleteGlossary(item.id)}
                      >
                        <Icon name="trash" size={14} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* Section 2: Verified Golden Metrics */}
      <section className="datasets-card semantic-section" aria-label="Chỉ số chuẩn nghiệp vụ">
        <div className="datasets-card-header">
          <div className="section-title-wrap">
            <h2>Chỉ số chuẩn nghiệp vụ (Verified Golden Metrics)</h2>
            <span className="badge-count emerald-count">{filteredMetrics.length} chỉ số</span>
          </div>
          <p className="section-subtitle">
            Công thức SQL chuẩn hóa được chuyên gia dữ liệu duyệt sẵn. Trợ lý AI sẽ ưu tiên áp dụng
            đúng các công thức này khi trả lời câu hỏi.
          </p>
        </div>

        {loading ? (
          <div className="datasets-loading">
            <span className="thinking-dots">
              <i />
              <i />
              <i />
            </span>
            <p>Đang tải danh sách chỉ số chuẩn…</p>
          </div>
        ) : filteredMetrics.length === 0 ? (
          <div className="datasets-empty">
            <Icon name="chart" size={32} />
            <p>Chưa có chỉ số chuẩn nào được đăng ký cho bộ dữ liệu này.</p>
            <button
              type="button"
              className="action-button-primary sharp-btn emerald-btn"
              onClick={() => setShowAddMetric(true)}
            >
              Thêm chỉ số chuẩn đầu tiên
            </button>
          </div>
        ) : (
          <div className="datasets-table-wrap">
            <table className="datasets-table sharp-table">
              <thead>
                <tr>
                  <th style={{ width: "22%" }}>Tên chỉ số (Display Name)</th>
                  <th style={{ width: "18%" }}>Mã định danh</th>
                  <th style={{ width: "28%" }}>Biểu thức SQL chuẩn (Golden Formula)</th>
                  <th style={{ width: "20%" }}>Diễn giải ý nghĩa</th>
                  <th style={{ width: "12%" }}>Dataset</th>
                  <th style={{ width: "8%", textAlign: "right" }}>Xóa</th>
                </tr>
              </thead>
              <tbody>
                {filteredMetrics.map((item) => (
                  <tr key={item.id ?? item.metric_name}>
                    <td>
                      <strong className="metric-display-name">{item.display_name}</strong>
                    </td>
                    <td>
                      <code className="code-badge">{item.metric_name}</code>
                    </td>
                    <td>
                      <code className="sql-formula-badge">{item.sql_expression}</code>
                    </td>
                    <td className="desc-cell">
                      {item.description || <span className="text-muted">—</span>}
                    </td>
                    <td>
                      <span className="dataset-tag">{getDatasetLabel(item.dataset_id)}</span>
                    </td>
                    <td style={{ textAlign: "right" }}>
                      <button
                        type="button"
                        className="btn-danger-icon"
                        title="Xóa chỉ số này"
                        onClick={() => handleDeleteMetric(item.id)}
                      >
                        <Icon name="trash" size={14} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* Modal: Thêm thuật ngữ */}
      {showAddGlossary && (
        <div className="modal-backdrop" onClick={() => !submitting && setShowAddGlossary(false)}>
          <div
            className="modal-content upload-modal sharp-modal"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="modal-header">
              <div>
                <h3 className="modal-title">Thêm thuật ngữ nghiệp vụ mới</h3>
                <p className="modal-subtitle">
                  Định nghĩa từ đồng nghĩa hoặc quy tắc ánh xạ tự nhiên
                </p>
              </div>
              <button
                type="button"
                className="icon-button"
                onClick={() => !submitting && setShowAddGlossary(false)}
                aria-label="Đóng"
              >
                <Icon name="close" size={16} />
              </button>
            </div>

            <form onSubmit={handleAddGlossarySubmit} className="upload-form">
              <div className="form-group">
                <label htmlFor="glossaryDataset">Bộ dữ liệu áp dụng</label>
                <select
                  id="glossaryDataset"
                  className="semantic-select"
                  value={glossaryDatasetId}
                  onChange={(e) => setGlossaryDatasetId(Number(e.target.value))}
                >
                  {datasets.map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.name} (#{d.id})
                    </option>
                  ))}
                </select>
              </div>

              <div className="form-group">
                <label htmlFor="glossaryTerm">Thuật ngữ hoặc cụm từ thường dùng (*)</label>
                <input
                  id="glossaryTerm"
                  type="text"
                  placeholder="vd: doanh thu, tiền tip, khách, cuốc xe..."
                  value={glossaryTerm}
                  onChange={(e) => setGlossaryTerm(e.target.value)}
                  required
                />
              </div>

              <div className="form-group">
                <label htmlFor="glossaryType">Loại ánh xạ</label>
                <select
                  id="glossaryType"
                  className="semantic-select"
                  value={glossaryTargetType}
                  onChange={(e) => setGlossaryTargetType(e.target.value)}
                >
                  <option value="column">Cột dữ liệu (column)</option>
                  <option value="metric">Chỉ số tính toán (metric)</option>
                  <option value="filter">Điều kiện lọc (filter)</option>
                </select>
              </div>

              <div className="form-group">
                <label htmlFor="glossaryTargetName">
                  Tên cột hoặc metric đích trong cơ sở dữ liệu (*)
                </label>
                <input
                  id="glossaryTargetName"
                  type="text"
                  placeholder="vd: total_amount, tip_amount, passenger_count..."
                  value={glossaryTargetName}
                  onChange={(e) => setGlossaryTargetName(e.target.value)}
                  required
                />
              </div>

              <div className="form-group">
                <label htmlFor="glossaryDesc">Mô tả / Ngữ cảnh nghiệp vụ (tùy chọn)</label>
                <textarea
                  id="glossaryDesc"
                  rows={2}
                  placeholder="Diễn giải ý nghĩa nghiệp vụ để LLM nắm rõ..."
                  value={glossaryDesc}
                  onChange={(e) => setGlossaryDesc(e.target.value)}
                />
              </div>

              {formError && <div className="form-error">{formError}</div>}

              <div className="modal-actions">
                <button
                  type="button"
                  className="action-btn-secondary sharp-btn"
                  onClick={() => setShowAddGlossary(false)}
                  disabled={submitting}
                >
                  Hủy
                </button>
                <button
                  type="submit"
                  className="action-button-primary sharp-btn"
                  disabled={submitting}
                >
                  {submitting ? "Đang lưu…" : "Lưu thuật ngữ"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal: Thêm chỉ số chuẩn */}
      {showAddMetric && (
        <div className="modal-backdrop" onClick={() => !submitting && setShowAddMetric(false)}>
          <div
            className="modal-content upload-modal sharp-modal"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="modal-header">
              <div>
                <h3 className="modal-title">Thêm chỉ số chuẩn (Verified Golden Metric)</h3>
                <p className="modal-subtitle">Xác thực công thức SQL chuẩn cho hệ thống BI</p>
              </div>
              <button
                type="button"
                className="icon-button"
                onClick={() => !submitting && setShowAddMetric(false)}
                aria-label="Đóng"
              >
                <Icon name="close" size={16} />
              </button>
            </div>

            <form onSubmit={handleAddMetricSubmit} className="upload-form">
              <div className="form-group">
                <label htmlFor="metricDataset">Bộ dữ liệu áp dụng</label>
                <select
                  id="metricDataset"
                  className="semantic-select"
                  value={metricDatasetId}
                  onChange={(e) => setMetricDatasetId(Number(e.target.value))}
                >
                  {datasets.map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.name} (#{d.id})
                    </option>
                  ))}
                </select>
              </div>

              <div className="form-group">
                <label htmlFor="metricDisplayName">Tên hiển thị chỉ số (*)</label>
                <input
                  id="metricDisplayName"
                  type="text"
                  placeholder="vd: Tổng Doanh Thu, Tỷ Lệ Tip Trung Bình..."
                  value={metricDisplayName}
                  onChange={(e) => setMetricDisplayName(e.target.value)}
                  required
                />
              </div>

              <div className="form-group">
                <label htmlFor="metricName">Mã định danh tiếng Anh (*)</label>
                <input
                  id="metricName"
                  type="text"
                  placeholder="vd: total_revenue, avg_tip_rate..."
                  value={metricName}
                  onChange={(e) => setMetricName(e.target.value)}
                  required
                />
              </div>

              <div className="form-group">
                <label htmlFor="metricSql">Biểu thức SQL chuẩn (Golden Formula) (*)</label>
                <input
                  id="metricSql"
                  type="text"
                  placeholder="vd: SUM(total_amount), AVG(tip_amount / NULLIF(fare_amount, 0))..."
                  value={metricSql}
                  onChange={(e) => setMetricSql(e.target.value)}
                  required
                />
                <small>Biểu thức hàm tổng hợp SQL tiêu chuẩn (SUM, AVG, COUNT...)</small>
              </div>

              <div className="form-group">
                <label htmlFor="metricDesc">Mô tả quy tắc tính (tùy chọn)</label>
                <textarea
                  id="metricDesc"
                  rows={2}
                  placeholder="Diễn giải quy chuẩn tính toán của chỉ số này..."
                  value={metricDesc}
                  onChange={(e) => setMetricDesc(e.target.value)}
                />
              </div>

              {formError && <div className="form-error">{formError}</div>}

              <div className="modal-actions">
                <button
                  type="button"
                  className="action-btn-secondary sharp-btn"
                  onClick={() => setShowAddMetric(false)}
                  disabled={submitting}
                >
                  Hủy
                </button>
                <button
                  type="submit"
                  className="action-button-primary sharp-btn emerald-btn"
                  disabled={submitting}
                >
                  {submitting ? "Đang lưu…" : "Lưu chỉ số chuẩn"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

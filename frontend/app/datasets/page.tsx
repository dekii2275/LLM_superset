"use client";

import { useEffect, useRef, useState } from "react";
import { AppLayout } from "@/components/layout/AppLayout";
import { Icon } from "@/components/ui/Icon";
import { SemanticLayerPanel } from "@/components/semantic/SemanticLayerPanel";
import { useDataset } from "@/context/DatasetContext";
import {
  getDashboardsList,
  previewDataset,
  updateDatasetDashboardSetting,
  uploadDataset,
} from "@/lib/api";
import type {
  DashboardOption,
  DatasetPreviewResult,
  DatasetSummary,
  UploadDatasetResult,
} from "@/lib/types";

export default function DatasetsPage() {
  const { datasets, activeDatasetId, setActiveDatasetId, refreshDatasets, loading } = useDataset();

  // Tabs
  const [activeTab, setActiveTab] = useState<"datasets" | "semantic">("datasets");

  // Modals & Drawers
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [showPreviewModal, setShowPreviewModal] = useState(false);

  // Upload state
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [customTableName, setCustomTableName] = useState("");
  const [customDescription, setCustomDescription] = useState("");
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploadSuccess, setUploadSuccess] = useState<UploadDatasetResult | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Preview state
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewData, setPreviewData] = useState<DatasetPreviewResult | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [previewingDatasetName, setPreviewingDatasetName] = useState("");

  // Dashboards list for dropdown
  const [dashboards, setDashboards] = useState<DashboardOption[]>([]);
  const [updatingDashboardId, setUpdatingDashboardId] = useState<number | null>(null);

  useEffect(() => {
    let active = true;
    void getDashboardsList().then((data) => {
      if (active) setDashboards(data);
    });
    return () => {
      active = false;
    };
  }, []);

  // Handle file drop & select
  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const file = e.target.files[0];
      setUploadFile(file);
      setUploadError(null);
      setUploadSuccess(null);
      if (!customTableName) {
        const base = file.name
          .replace(/\.[^/.]+$/, "")
          .replace(/[^a-zA-Z0-9_]/g, "_")
          .toLowerCase();
        setCustomTableName(base);
      }
    }
  };

  // Submit upload
  const handleUploadSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!uploadFile) return;

    setUploading(true);
    setUploadError(null);
    setUploadSuccess(null);

    try {
      const res = await uploadDataset(
        uploadFile,
        customTableName || undefined,
        customDescription || undefined,
      );
      setUploadSuccess(res);
      await refreshDatasets();
      if (res.dataset_id) {
        setActiveDatasetId(res.dataset_id);
      }
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : "Tải lên tệp thất bại.");
    } finally {
      setUploading(false);
    }
  };

  // Trigger preview
  const handleOpenPreview = async (ds: DatasetSummary) => {
    setPreviewingDatasetName(ds.name || ds.table_name);
    setShowPreviewModal(true);
    setPreviewLoading(true);
    setPreviewError(null);
    setPreviewData(null);

    try {
      const data = await previewDataset(ds.id, 20);
      setPreviewData(data);
    } catch (err) {
      setPreviewError(err instanceof Error ? err.message : "Không thể xem trước dữ liệu.");
    } finally {
      setPreviewLoading(false);
    }
  };

  // Toggle dashboard status
  const handleToggleDashboard = async (ds: DatasetSummary) => {
    const isCurrentlyEnabled = Boolean(ds.default_dashboard_id);
    const nextEnabled = !isCurrentlyEnabled;
    const matchingDash = dashboards.find(
      (d) =>
        d.title.toLowerCase().includes(ds.name.toLowerCase()) ||
        d.title.toLowerCase().includes(ds.table_name.toLowerCase()),
    );
    const nextDashId = nextEnabled
      ? ds.default_dashboard_id || (matchingDash ? matchingDash.id : null)
      : null;

    if (nextEnabled && !nextDashId) {
      alert(
        `Bộ dữ liệu "${ds.name}" hiện chưa có bảng điều khiển riêng trong Superset. Bạn có thể chat với AI ở trang chủ để tự động tạo bảng điều khiển mới!`,
      );
      return;
    }

    setUpdatingDashboardId(ds.id);
    try {
      await updateDatasetDashboardSetting(ds.id, nextDashId, nextEnabled);
      await refreshDatasets();
    } catch (err) {
      alert(err instanceof Error ? err.message : "Lỗi khi cập nhật bảng điều khiển.");
    } finally {
      setUpdatingDashboardId(null);
    }
  };

  // Change assigned dashboard
  const handleAssignDashboard = async (ds: DatasetSummary, newDashId: number) => {
    setUpdatingDashboardId(ds.id);
    try {
      await updateDatasetDashboardSetting(ds.id, newDashId, true);
      await refreshDatasets();
    } catch (err) {
      alert(err instanceof Error ? err.message : "Lỗi khi cập nhật bảng điều khiển.");
    } finally {
      setUpdatingDashboardId(null);
    }
  };

  return (
    <AppLayout singleColumn>
      <div className="route-page datasets-page" aria-label="Quản lý nguồn dữ liệu">
        <header className="route-heading datasets-heading">
          <div className="datasets-header-top">
            <div>
              <p className="panel-eyebrow">DỮ LIỆU & NGUỒN PHÂN TÍCH</p>
              <h1>Quản lý dữ liệu & Ngữ nghĩa</h1>
              <p>
                Tải lên tệp CSV/Parquet, xem trước bảng dữ liệu, cấu hình bảng điều khiển và quản lý
                từ điển nghiệp vụ.
              </p>
            </div>
            {activeTab === "datasets" && (
              <button
                className="action-button-primary upload-trigger-btn sharp-btn"
                type="button"
                onClick={() => {
                  setShowUploadModal(true);
                  setUploadError(null);
                  setUploadSuccess(null);
                  setUploadFile(null);
                  setCustomTableName("");
                  setCustomDescription("");
                }}
              >
                <Icon name="plus" size={16} />
                <span>Tải lên tệp dữ liệu</span>
              </button>
            )}
          </div>

          <div className="tab-switcher-nav" role="tablist">
            <button
              type="button"
              role="tab"
              aria-selected={activeTab === "datasets"}
              className={`tab-switch-btn ${activeTab === "datasets" ? "active" : ""}`}
              onClick={() => setActiveTab("datasets")}
            >
              <Icon name="database" size={15} />
              <span>Nguồn dữ liệu & Tệp tin</span>
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={activeTab === "semantic"}
              className={`tab-switch-btn ${activeTab === "semantic" ? "active" : ""}`}
              onClick={() => setActiveTab("semantic")}
            >
              <Icon name="book" size={15} />
              <span>Tầng ngữ nghĩa & Chỉ số chuẩn (Semantic Layer)</span>
            </button>
          </div>

          {activeTab === "datasets" && (
            <div className="datasets-metrics-grid">
              <div className="datasets-metric-card">
                <div className="metric-top-row">
                  <span className="metric-label">Tổng số Datasets</span>
                  <span className="metric-icon-wrap emerald">
                    <Icon name="database" size={17} />
                  </span>
                </div>
                <div className="metric-val">{datasets.length}</div>
                <div className="metric-hint">
                  <span className="hint-dot emerald" />
                  <span>Đã đăng ký trong Superset</span>
                </div>
              </div>

              <div className="datasets-metric-card">
                <div className="metric-top-row">
                  <span className="metric-label">Dashboard liên kết</span>
                  <span className="metric-icon-wrap blue">
                    <Icon name="sparkle" size={17} />
                  </span>
                </div>
                <div className="metric-val">
                  {datasets.filter((d) => Boolean(d.default_dashboard_id)).length}
                </div>
                <div className="metric-hint">
                  <span className="hint-dot blue" />
                  <span>Đang bật hiển thị nhúng</span>
                </div>
              </div>

              <div className="datasets-metric-card">
                <div className="metric-top-row">
                  <span className="metric-label">Dataset hiện tại</span>
                  <span className="metric-icon-wrap purple">
                    <Icon name="code" size={17} />
                  </span>
                </div>
                <div className="metric-val truncate-text">
                  {datasets.find((d) => d.id === activeDatasetId)?.name || "Chưa chọn"}
                </div>
                <div className="metric-hint">
                  <span className="hint-dot purple" />
                  <span>Đang trỏ để phân tích hội thoại</span>
                </div>
              </div>
            </div>
          )}
        </header>

        {activeTab === "datasets" ? (
          <section className="datasets-card" aria-label="Danh sách dataset">
            <div className="datasets-card-header">
              <h2>Danh sách nguồn dữ liệu ({datasets.length})</h2>
              <button
                className="refresh-btn"
                type="button"
                onClick={() => void refreshDatasets()}
                title="Làm mới danh sách"
              >
                <Icon name="sparkle" size={15} />
              </button>
            </div>

            {loading && datasets.length === 0 ? (
              <div className="datasets-loading">
                <span className="thinking-dots">
                  <i />
                  <i />
                  <i />
                </span>
                <p>Đang tải danh sách nguồn dữ liệu từ Superset…</p>
              </div>
            ) : datasets.length === 0 ? (
              <div className="datasets-empty">
                <Icon name="database" size={40} />
                <p>Chưa có dataset nào được kết nối.</p>
                <button
                  className="upload-trigger-btn"
                  type="button"
                  onClick={() => setShowUploadModal(true)}
                >
                  Tải lên tệp dữ liệu đầu tiên
                </button>
              </div>
            ) : (
              <div className="datasets-table-wrap">
                <table className="datasets-table">
                  <thead>
                    <tr>
                      <th>Nguồn dữ liệu</th>
                      <th>Bảng SQL / Schema</th>
                      <th>Cột & Metrics</th>
                      <th>Bảng điều khiển (Dashboard)</th>
                      <th style={{ textAlign: "right" }}>Thao tác</th>
                    </tr>
                  </thead>
                  <tbody>
                    {datasets.map((ds) => {
                      const isActive = ds.id === activeDatasetId;
                      const hasDashboard = Boolean(ds.default_dashboard_id);
                      const isBusy = updatingDashboardId === ds.id;

                      return (
                        <tr key={ds.id} className={isActive ? "row-active" : ""}>
                          <td>
                            <div className="dataset-name-cell">
                              <span className="dataset-id-tag">#{ds.id}</span>
                              <div>
                                <span className="dataset-name-title">{ds.name}</span>
                                {isActive && <span className="active-badge">✓ Đang chọn</span>}
                                {ds.description && <p className="dataset-desc">{ds.description}</p>}
                              </div>
                            </div>
                          </td>
                          <td>
                            <code className="sql-table-tag">raw.{ds.table_name}</code>
                          </td>
                          <td>
                            <div className="dataset-stats-pill">
                              <span className="pill-col">{ds.column_count} cột</span>
                              <span className="pill-metric">{ds.metric_count} metrics</span>
                            </div>
                          </td>
                          <td>
                            <div className="dashboard-control-group">
                              <button
                                type="button"
                                className={`dashboard-toggle-btn ${hasDashboard ? "is-on" : "is-off"}`}
                                onClick={() => void handleToggleDashboard(ds)}
                                disabled={isBusy}
                                title={
                                  hasDashboard
                                    ? "Bấm để tắt bảng điều khiển"
                                    : "Bấm để bật bảng điều khiển"
                                }
                              >
                                <span className="toggle-indicator" />
                                <span>{hasDashboard ? "Đang bật" : "Đã tắt"}</span>
                              </button>

                              {hasDashboard && (
                                <select
                                  className="dashboard-assign-select"
                                  value={ds.default_dashboard_id ?? ""}
                                  disabled={isBusy}
                                  onChange={(e) =>
                                    void handleAssignDashboard(ds, Number(e.target.value))
                                  }
                                  aria-label="Chọn bảng điều khiển liên kết"
                                >
                                  {dashboards.map((dash) => (
                                    <option key={dash.id} value={dash.id}>
                                      {dash.title}
                                    </option>
                                  ))}
                                </select>
                              )}
                            </div>
                          </td>
                          <td style={{ textAlign: "right" }}>
                            <div className="dataset-row-actions">
                              <button
                                type="button"
                                className="action-btn-secondary"
                                onClick={() => void handleOpenPreview(ds)}
                                title="Xem trước cấu trúc và dữ liệu bảng"
                              >
                                <Icon name="code" size={13} />
                                <span>Xem trước</span>
                              </button>

                              {!isActive ? (
                                <button
                                  type="button"
                                  className="action-btn-primary"
                                  onClick={() => setActiveDatasetId(ds.id)}
                                  title="Đặt làm nguồn phân tích chính trong thanh điều hướng"
                                >
                                  <span>Chọn</span>
                                </button>
                              ) : (
                                <span className="chosen-indicator">✓ Hiện tại</span>
                              )}
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        ) : (
          <SemanticLayerPanel datasets={datasets} activeDatasetId={activeDatasetId} />
        )}

        {/* Upload Modal */}
        {showUploadModal && (
          <div className="modal-backdrop" onClick={() => !uploading && setShowUploadModal(false)}>
            <div className="modal-content upload-modal" onClick={(e) => e.stopPropagation()}>
              <div className="modal-header">
                <div>
                  <h3 className="modal-title">Tải lên tệp dữ liệu mới</h3>
                  <p className="modal-subtitle">Hỗ trợ các tệp định dạng .CSV và .Parquet</p>
                </div>
                <button
                  type="button"
                  className="icon-button"
                  onClick={() => !uploading && setShowUploadModal(false)}
                  aria-label="Đóng"
                >
                  <Icon name="close" size={16} />
                </button>
              </div>

              {uploadSuccess ? (
                <div className="upload-success-pane">
                  <div className="success-icon-wrap">✓</div>
                  <h4>Tải lên và nạp dữ liệu thành công!</h4>
                  <p>
                    Bảng <code>raw.{uploadSuccess.table_name}</code> đã sẵn sàng với{" "}
                    <strong>{uploadSuccess.row_count.toLocaleString()} dòng</strong> và{" "}
                    <strong>{uploadSuccess.column_count} cột</strong>.
                  </p>
                  <div className="success-actions">
                    <button
                      type="button"
                      className="action-button-primary"
                      onClick={() => setShowUploadModal(false)}
                    >
                      Hoàn thành
                    </button>
                  </div>
                </div>
              ) : (
                <form onSubmit={handleUploadSubmit} className="upload-form">
                  <div
                    className={`dropzone ${uploadFile ? "has-file" : ""}`}
                    onClick={() => fileInputRef.current?.click()}
                  >
                    <input
                      ref={fileInputRef}
                      type="file"
                      accept=".csv,.parquet,.pq"
                      onChange={handleFileChange}
                      style={{ display: "none" }}
                    />
                    <Icon name="database" size={32} />
                    {uploadFile ? (
                      <div className="dropzone-file-info">
                        <strong>{uploadFile.name}</strong>
                        <span>{(uploadFile.size / 1024 / 1024).toFixed(2)} MB</span>
                        <span className="re-select-hint">Bấm để chọn tệp khác</span>
                      </div>
                    ) : (
                      <div className="dropzone-text">
                        <strong>Kéo thả tệp vào đây hoặc bấm để chọn tệp</strong>
                        <span>Chấp nhận file định dạng .CSV hoặc .Parquet</span>
                      </div>
                    )}
                  </div>

                  <div className="form-group">
                    <label htmlFor="customTableName">Tên bảng SQL (tùy chọn)</label>
                    <input
                      id="customTableName"
                      type="text"
                      placeholder="vd: sales_data_2026"
                      value={customTableName}
                      onChange={(e) => setCustomTableName(e.target.value)}
                    />
                    <small>
                      Sẽ được tạo dưới schema <code>raw.&lt;tên_bảng&gt;</code> trong PostgreSQL
                    </small>
                  </div>

                  <div className="form-group">
                    <label htmlFor="customDescription">Mô tả dữ liệu (tùy chọn)</label>
                    <textarea
                      id="customDescription"
                      rows={2}
                      placeholder="Mô tả nội dung hoặc ngữ cảnh của bộ dữ liệu này..."
                      value={customDescription}
                      onChange={(e) => setCustomDescription(e.target.value)}
                    />
                  </div>

                  {uploadError && <div className="form-error">{uploadError}</div>}

                  <div className="modal-actions">
                    <button
                      type="button"
                      className="action-btn-secondary"
                      onClick={() => setShowUploadModal(false)}
                      disabled={uploading}
                    >
                      Hủy
                    </button>
                    <button
                      type="submit"
                      className="action-button-primary"
                      disabled={!uploadFile || uploading}
                    >
                      {uploading ? "Đang xử lý và nạp dữ liệu…" : "Nạp vào Database & Superset"}
                    </button>
                  </div>
                </form>
              )}
            </div>
          </div>
        )}

        {/* Data Preview Modal */}
        {showPreviewModal && (
          <div className="modal-backdrop" onClick={() => setShowPreviewModal(false)}>
            <div className="modal-content preview-modal" onClick={(e) => e.stopPropagation()}>
              <div className="modal-header">
                <div>
                  <h3 className="modal-title">Xem trước dữ liệu: {previewingDatasetName}</h3>
                  {previewData && (
                    <p className="modal-subtitle">
                      Bảng <code>raw.{previewData.table_name}</code> · Tổng số dòng:{" "}
                      <strong>{previewData.total_rows.toLocaleString()}</strong> · Số cột:{" "}
                      <strong>{previewData.column_count}</strong>
                    </p>
                  )}
                </div>
                <button
                  type="button"
                  className="icon-button"
                  onClick={() => setShowPreviewModal(false)}
                  aria-label="Đóng"
                >
                  <Icon name="close" size={16} />
                </button>
              </div>

              {previewLoading ? (
                <div className="preview-loading">
                  <span className="thinking-dots">
                    <i />
                    <i />
                    <i />
                  </span>
                  <p>Đang tải dữ liệu từ PostgreSQL…</p>
                </div>
              ) : previewError ? (
                <div className="form-error">{previewError}</div>
              ) : previewData ? (
                <div className="preview-body">
                  <div className="columns-badges-row">
                    {previewData.columns.map((c) => (
                      <span key={c.name} className="col-type-badge">
                        <b>{c.name}</b>
                        <small>{c.type}</small>
                      </span>
                    ))}
                  </div>

                  <div className="preview-grid-wrap">
                    <table className="preview-grid">
                      <thead>
                        <tr>
                          {previewData.columns.map((c) => (
                            <th key={c.name}>{c.name}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {previewData.rows.map((row, idx) => (
                          <tr key={idx}>
                            {previewData.columns.map((c) => (
                              <td key={c.name}>{String(row[c.name] ?? "")}</td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              ) : null}
            </div>
          </div>
        )}
      </div>
    </AppLayout>
  );
}

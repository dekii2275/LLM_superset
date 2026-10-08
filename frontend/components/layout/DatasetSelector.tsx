"use client";

import { useDataset } from "@/context/DatasetContext";
import { Icon } from "@/components/ui/Icon";
import type { DatasetSummary } from "@/lib/types";

type DatasetSelectorProps = {
  activeDatasetId?: number | null;
  onSelectDataset?: (datasetId: number, dataset?: DatasetSummary) => void;
};

export function DatasetSelector({
  activeDatasetId: propActiveId,
  onSelectDataset: propOnSelect,
}: DatasetSelectorProps) {
  const context = useDataset();
  const datasets = context.datasets;
  const loading = context.loading;
  const activeDatasetId = propActiveId ?? context.activeDatasetId;
  const currentDataset = datasets.find((d) => d.id === activeDatasetId) || datasets[0];

  const handleSelect = (nextId: number) => {
    context.setActiveDatasetId(nextId);
    const selectedDs = datasets.find((d) => d.id === nextId);
    if (propOnSelect) propOnSelect(nextId, selectedDs);
  };

  return (
    <div className="dataset-selector-wrap" aria-label="Nguồn dữ liệu phân tích">
      <div className="dataset-selector-pill">
        <span className="dataset-icon">
          <Icon name="database" size={15} />
        </span>
        <select
          className="dataset-select"
          value={activeDatasetId ?? (currentDataset?.id || "")}
          disabled={loading || datasets.length === 0}
          onChange={(e) => handleSelect(Number(e.target.value))}
          aria-label="Chọn nguồn dữ liệu"
        >
          {datasets.length === 0 ? (
            <option value="">{loading ? "Đang tải dữ liệu…" : "Không có dataset"}</option>
          ) : (
            datasets.map((ds) => (
              <option key={ds.id} value={ds.id}>
                {ds.name || ds.table_name} ({ds.column_count} cột)
              </option>
            ))
          )}
        </select>
        {currentDataset && (
          <span className="dataset-meta-badge" title={currentDataset.description || ""}>
            {currentDataset.metric_count > 0 ? `${currentDataset.metric_count} metrics` : "Dataset"}
          </span>
        )}
      </div>
    </div>
  );
}

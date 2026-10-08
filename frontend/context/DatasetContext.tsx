"use client";

import React, { createContext, useCallback, useContext, useEffect, useState } from "react";
import { getDatasets } from "@/lib/api";
import type { DatasetSummary } from "@/lib/types";

type DatasetContextType = {
  datasets: DatasetSummary[];
  activeDatasetId: number | null;
  activeDataset: DatasetSummary | null;
  setActiveDatasetId: (id: number) => void;
  refreshDatasets: () => Promise<void>;
  loading: boolean;
};

const DatasetContext = createContext<DatasetContextType | undefined>(undefined);

const STORAGE_KEY = "ai_bi_active_dataset_id";

export function DatasetProvider({ children }: { children: React.ReactNode }) {
  const [datasets, setDatasets] = useState<DatasetSummary[]>([]);
  const [activeDatasetId, setActiveDatasetIdState] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);

  const refreshDatasets = useCallback(async () => {
    try {
      setLoading(true);
      const data = await getDatasets();
      setDatasets(data);
      if (data.length > 0) {
        // Retrieve stored dataset ID if valid
        const stored = typeof window !== "undefined" ? localStorage.getItem(STORAGE_KEY) : null;
        const storedId = stored ? Number(stored) : null;
        const matched = storedId && data.find((d) => d.id === storedId);

        setActiveDatasetIdState((prev) => {
          if (prev && data.some((d) => d.id === prev)) {
            return prev;
          }
          if (matched) {
            return matched.id;
          }
          return data[0].id;
        });
      }
    } catch {
      // Keep existing datasets on network error
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refreshDatasets();
  }, [refreshDatasets]);

  const setActiveDatasetId = useCallback((id: number) => {
    setActiveDatasetIdState(id);
    if (typeof window !== "undefined") {
      try {
        localStorage.setItem(STORAGE_KEY, String(id));
      } catch {
        // ignore storage errors
      }
    }
  }, []);

  const activeDataset = datasets.find((d) => d.id === activeDatasetId) || datasets[0] || null;

  return (
    <DatasetContext.Provider
      value={{
        datasets,
        activeDatasetId: activeDataset?.id ?? null,
        activeDataset,
        setActiveDatasetId,
        refreshDatasets,
        loading,
      }}
    >
      {children}
    </DatasetContext.Provider>
  );
}

export function useDataset(): DatasetContextType {
  const context = useContext(DatasetContext);
  if (!context) {
    throw new Error("useDataset must be used within a DatasetProvider");
  }
  return context;
}

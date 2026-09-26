"use client";

import { useEffect, useRef, useState } from "react";
import { embedDashboard } from "@superset-ui/embedded-sdk";
import { apiUrl } from "@/lib/api";

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
    const detail = await response.json().catch(() => null) as { detail?: string } | null;
    throw new Error(detail?.detail ?? "Không thể kết nối với Superset.");
  }
  return response.json() as Promise<T>;
}

export function EmbeddedDashboard({ onClose, dashboardId, title, variant = "page" }: EmbeddedDashboardProps) {
  const mountPoint = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);

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

  return (
    <section
      className={`superset-embed ${variant === "inline" ? "superset-embed-inline" : ""}`}
      role={variant === "inline" ? undefined : "dialog"}
      aria-modal={variant === "inline" ? undefined : true}
      aria-label="Bảng điều khiển Superset được nhúng"
    >
      <div className="superset-embed-header">
        <div>
          <p className="panel-eyebrow">BẢNG ĐIỀU KHIỂN TRỰC TIẾP</p>
          <h2>{title ?? "Phân tích chuyến đi Taxi NYC"}</h2>
        </div>
        <button type="button" className="superset-close" onClick={onClose}>Quay lại phân tích</button>
      </div>
      {error ? <p className="superset-embed-error">{error}</p> : <div ref={mountPoint} className="superset-embed-frame" />}
    </section>
  );
}

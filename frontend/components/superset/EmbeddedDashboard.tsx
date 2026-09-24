"use client";

import { useEffect, useRef, useState } from "react";
import { embedDashboard } from "@superset-ui/embedded-sdk";
import { apiUrl } from "@/lib/api";

type EmbedConfig = {
  dashboard_id: string;
  superset_url: string;
};

type EmbeddedDashboardProps = {
  onClose: () => void;
  dashboardId?: number;
  title?: string;
};

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(apiUrl(path), { cache: "no-store" });
  if (!response.ok) {
    const detail = await response.json().catch(() => null) as { detail?: string } | null;
    throw new Error(detail?.detail ?? "Could not connect to Superset.");
  }
  return response.json() as Promise<T>;
}

export function EmbeddedDashboard({ onClose, dashboardId, title }: EmbeddedDashboardProps) {
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
            hideTab: true,
            hideChartControls: true,
            filters: { expanded: false },
          },
        });
      } catch (embedError) {
        if (!cancelled) {
          setError(embedError instanceof Error ? embedError.message : "Could not load Superset.");
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
      className="superset-embed"
      role="dialog"
      aria-modal="true"
      aria-label="Embedded Superset dashboard"
    >
      <div className="superset-embed-header">
        <div>
          <p className="panel-eyebrow">LIVE DASHBOARD</p>
          <h2>{title ?? "NYC Yellow Taxi Overview"}</h2>
        </div>
        <button type="button" className="superset-close" onClick={onClose}>Back to analysis</button>
      </div>
      {error ? <p className="superset-embed-error">{error}</p> : <div ref={mountPoint} className="superset-embed-frame" />}
    </section>
  );
}

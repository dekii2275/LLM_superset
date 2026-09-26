"use client";

import { useEffect, useState } from "react";
import { apiUrl, checkEndpoint } from "@/lib/api";

type ApiState = "checking" | "connected" | "disconnected";

export function ServiceStatus() {
  const [apiState, setApiState] = useState<ApiState>("checking");

  useEffect(() => {
    let active = true;
    const checkApi = async () => {
      const available = await checkEndpoint(apiUrl("/health"));
      if (active) setApiState(available ? "connected" : "disconnected");
    };

    void checkApi();
    const timer = window.setInterval(() => void checkApi(), 30_000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, []);

  return (
    <div className="service-status" aria-label="Trạng thái hệ thống">
      <div className="service-status-item" aria-live="polite">
        <span className={`status-dot ${apiState}`} />
        <span className="service-status-name">API</span>
        <span className="service-status-value">
          {apiState === "checking" ? "Đang kiểm tra" : apiState === "connected" ? "Trực tuyến" : "Ngoại tuyến"}
        </span>
      </div>
      <div className="service-status-item">
        <span className="status-dot connected" />
        <span className="service-status-name">Superset</span>
        <span className="service-status-value">Trực tuyến</span>
      </div>
    </div>
  );
}

"use client";

import React, { useState, useEffect, useRef } from "react";
import type { AlertItem } from "@/lib/types";
import { getAlertsApi, markAlertReadApi, markAllAlertsReadApi, scanAnomaliesApi } from "@/lib/api";

type AlertsDropdownProps = {
  activeDatasetId?: number | null;
  onSelectQuery?: (queryText: string) => void;
};

export function AlertsDropdown({ activeDatasetId, onSelectQuery }: AlertsDropdownProps) {
  const [alerts, setAlerts] = useState<AlertItem[]>([]);
  const [unreadCount, setUnreadCount] = useState<number>(0);
  const [isOpen, setIsOpen] = useState<boolean>(false);
  const [scanning, setScanning] = useState<boolean>(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const fetchAlerts = async () => {
    try {
      const data = await getAlertsApi();
      setAlerts(data.alerts);
      setUnreadCount(data.unread_count);
    } catch {
      // ignore network errors
    }
  };

  useEffect(() => {
    fetchAlerts();
    const interval = setInterval(fetchAlerts, 30000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const handleMarkAllRead = async () => {
    await markAllAlertsReadApi();
    await fetchAlerts();
  };

  const handleMarkRead = async (id: number) => {
    await markAlertReadApi(id);
    await fetchAlerts();
  };

  const handleScan = async () => {
    setScanning(true);
    try {
      await scanAnomaliesApi(activeDatasetId || 1);
      await fetchAlerts();
    } finally {
      setScanning(false);
    }
  };

  return (
    <div className="alerts-wrap" ref={dropdownRef}>
      <button
        type="button"
        onClick={() => setIsOpen((open) => !open)}
        className="alerts-bell-btn"
        aria-label="Thông báo và cảnh báo bất thường"
      >
        <span>🔔</span>
        {unreadCount > 0 && (
          <span className="alerts-badge">{unreadCount > 9 ? "9+" : unreadCount}</span>
        )}
      </button>

      {isOpen && (
        <div className="alerts-dropdown-box">
          <div className="alerts-dropdown-header">
            <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
              <span style={{ fontSize: "14px" }}>🔔</span>
              <span
                style={{
                  fontSize: "11px",
                  fontWeight: 700,
                  textTransform: "uppercase",
                  letterSpacing: "0.05em",
                }}
              >
                Cảnh báo thông minh
              </span>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
              <button
                type="button"
                onClick={handleScan}
                disabled={scanning}
                style={{
                  fontSize: "11px",
                  background: "#334155",
                  color: "#FFFFFF",
                  border: "none",
                  borderRadius: "4px",
                  padding: "2px 8px",
                  cursor: "pointer",
                }}
              >
                {scanning ? "Đang quét..." : "⚡ Quét"}
              </button>
              {unreadCount > 0 && (
                <button
                  type="button"
                  onClick={handleMarkAllRead}
                  style={{
                    fontSize: "11px",
                    background: "transparent",
                    color: "#7DD3FC",
                    border: "none",
                    cursor: "pointer",
                    textDecoration: "underline",
                  }}
                >
                  Đọc hết
                </button>
              )}
            </div>
          </div>

          <div className="alerts-dropdown-list">
            {alerts.length === 0 ? (
              <div
                style={{ padding: "24px", textAlign: "center", fontSize: "12px", color: "#94A3B8" }}
              >
                Không có cảnh báo bất thường nào.
              </div>
            ) : (
              alerts.map((alert) => {
                const isCrit = alert.severity === "critical";
                const isWarn = alert.severity === "warning";
                const badgeBg = isCrit ? "#FEE2E2" : isWarn ? "#FEF3C7" : "#E0F2FE";
                const badgeColor = isCrit ? "#B91C1C" : isWarn ? "#B45309" : "#0369A1";

                return (
                  <div
                    key={alert.id}
                    className={`alert-item-card ${!alert.is_read ? "unread" : ""}`}
                  >
                    <div
                      style={{
                        display: "flex",
                        alignItems: "flex-start",
                        justifyContent: "space-between",
                        gap: "8px",
                      }}
                    >
                      <div
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: "6px",
                          flexWrap: "wrap",
                        }}
                      >
                        <span
                          style={{
                            fontSize: "9px",
                            fontWeight: 700,
                            padding: "1px 5px",
                            borderRadius: "3px",
                            background: badgeBg,
                            color: badgeColor,
                            textTransform: "uppercase",
                          }}
                        >
                          {alert.severity}
                        </span>
                        <strong style={{ fontSize: "12px", color: "#0F172A" }}>
                          {alert.title}
                        </strong>
                      </div>
                      {!alert.is_read && (
                        <button
                          type="button"
                          onClick={() => handleMarkRead(alert.id)}
                          style={{
                            border: "none",
                            background: "transparent",
                            color: "#94A3B8",
                            cursor: "pointer",
                            fontSize: "12px",
                            padding: "0 2px",
                          }}
                          title="Đánh dấu đã đọc"
                        >
                          ✓
                        </button>
                      )}
                    </div>

                    <p
                      style={{
                        margin: "4px 0 0",
                        fontSize: "11px",
                        color: "#475569",
                        lineHeight: 1.4,
                      }}
                    >
                      {alert.message}
                    </p>

                    {alert.suggested_query && onSelectQuery && (
                      <button
                        type="button"
                        onClick={() => {
                          onSelectQuery(alert.suggested_query!);
                          setIsOpen(false);
                        }}
                        style={{
                          marginTop: "6px",
                          fontSize: "11px",
                          color: "#0284C7",
                          background: "transparent",
                          border: "none",
                          cursor: "pointer",
                          padding: 0,
                          textAlign: "left",
                          textDecoration: "underline",
                        }}
                      >
                        🔍 {alert.suggested_query}
                      </button>
                    )}
                  </div>
                );
              })
            )}
          </div>
        </div>
      )}
    </div>
  );
}

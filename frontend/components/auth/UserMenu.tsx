"use client";

import React, { useState, useRef, useEffect } from "react";
import { useAuth } from "@/context/AuthContext";
import { clearSemanticCacheApi } from "@/lib/api";

type UserMenuProps = {
  activeDatasetId?: number | null;
};

export function UserMenu({ activeDatasetId }: UserMenuProps) {
  const { user, demoUsers, quickSwitchUser, setIsLoginModalOpen, logout } = useAuth();
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [cacheMessage, setCacheMessage] = useState<string | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setDropdownOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  if (!user) {
    return (
      <button
        onClick={() => setIsLoginModalOpen(true)}
        className="user-menu-btn"
        style={{ background: "#0E4A86", color: "#FFFFFF", fontWeight: 600 }}
        type="button"
      >
        <span>👤</span>
        <span>Đăng nhập</span>
      </button>
    );
  }

  // Find active RLS rule for currently active dataset
  const currentRls = activeDatasetId
    ? user.rls_rules.find((r) => r.dataset_id === activeDatasetId)
    : user.rls_rules[0];

  const isAdmin = user.role === "admin";

  const handleClearCache = async () => {
    try {
      await clearSemanticCacheApi();
      setCacheMessage("Đã làm mới Semantic Cache!");
      setTimeout(() => setCacheMessage(null), 3000);
    } catch {
      setCacheMessage("Lỗi xóa cache");
      setTimeout(() => setCacheMessage(null), 3000);
    }
  };

  return (
    <div className="user-menu-wrap" ref={menuRef}>
      <button
        type="button"
        onClick={() => setDropdownOpen((open) => !open)}
        className="user-menu-btn"
        aria-haspopup="true"
        aria-expanded={dropdownOpen}
      >
        <span className="user-avatar-circle">
          {isAdmin ? "👑" : user.username[0].toUpperCase()}
        </span>
        <div
          style={{ display: "flex", flexDirection: "column", textAlign: "left", lineHeight: 1.2 }}
        >
          <strong style={{ fontSize: "12px", color: "#0F172A" }}>{user.username}</strong>
          <span style={{ fontSize: "10px", color: "#64748B" }}>
            {isAdmin ? "Toàn quyền" : currentRls ? "🔒 RLS" : "Manager"}
          </span>
        </div>
        <span style={{ fontSize: "10px", color: "#94A3B8", marginLeft: "2px" }}>▾</span>
      </button>

      {dropdownOpen && (
        <div className="user-menu-dropdown">
          <div className="user-menu-dropdown-header">
            <p style={{ margin: 0, fontWeight: 700, fontSize: "12px", color: "#0F172A" }}>
              {user.display_name}
            </p>
            <p style={{ margin: "2px 0 0", fontSize: "11px", color: "#64748B" }}>
              Vai trò:{" "}
              <strong style={{ color: "#0284C7", textTransform: "uppercase" }}>{user.role}</strong>
            </p>

            {currentRls ? (
              <div
                style={{
                  marginTop: "8px",
                  padding: "8px",
                  background: "#FEF3C7",
                  border: "1px solid #FCD34D",
                  borderRadius: "6px",
                  fontSize: "11px",
                  color: "#92400E",
                }}
              >
                <span
                  style={{ fontWeight: 700, display: "flex", alignItems: "center", gap: "4px" }}
                >
                  🔒 Phân quyền RLS đang áp dụng:
                </span>
                <p
                  style={{
                    margin: "4px 0 2px",
                    fontFamily: "monospace",
                    fontSize: "10px",
                    background: "rgba(255,255,255,0.7)",
                    padding: "4px 6px",
                    borderRadius: "4px",
                  }}
                >
                  {currentRls.filter_clause}
                </p>
                <p style={{ margin: 0, fontSize: "10px", color: "#B45309" }}>
                  {currentRls.description}
                </p>
              </div>
            ) : (
              <div
                style={{
                  marginTop: "8px",
                  padding: "6px 8px",
                  background: "#ECFDF5",
                  border: "1px solid #A7F3D0",
                  borderRadius: "6px",
                  fontSize: "11px",
                  color: "#047857",
                }}
              >
                ✨ Không bị giới hạn (Xem toàn bộ dữ liệu)
              </div>
            )}
          </div>

          <div className="user-menu-dropdown-section">
            <div className="user-menu-dropdown-section-title">
              Chuyển nhanh tài khoản demo (RLS):
            </div>
            {demoUsers.map((u) => {
              const active = u.username === user.username;
              return (
                <button
                  key={u.id}
                  type="button"
                  onClick={async () => {
                    await quickSwitchUser(u);
                    setDropdownOpen(false);
                  }}
                  className={`user-demo-btn ${active ? "active" : ""}`}
                >
                  <span
                    style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
                  >
                    {u.username === "admin" ? "👑" : "👤"} {u.display_name}
                  </span>
                  {active && <span style={{ color: "#0284C7", fontWeight: 700 }}>✓</span>}
                </button>
              );
            })}
          </div>

          <div style={{ padding: "6px 8px", background: "#F8FAFC" }}>
            <button type="button" onClick={handleClearCache} className="user-menu-footer-btn">
              <span>⚡</span>
              <span>Xóa Semantic Cache (Redis)</span>
            </button>
            {cacheMessage && (
              <p
                style={{
                  margin: "2px 0 4px",
                  fontSize: "10px",
                  color: "#059669",
                  fontWeight: 600,
                  padding: "0 10px",
                }}
              >
                {cacheMessage}
              </p>
            )}

            <button
              type="button"
              onClick={() => {
                logout();
                setDropdownOpen(false);
              }}
              className="user-menu-footer-btn logout"
            >
              <span>🚪</span>
              <span>Đăng xuất / Đổi tài khoản</span>
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

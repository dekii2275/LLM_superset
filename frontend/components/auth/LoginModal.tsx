"use client";

import React, { useState } from "react";
import { useAuth } from "@/context/AuthContext";

export function LoginModal() {
  const { user, isLoginModalOpen, setIsLoginModalOpen, login, loginAsAdmin, loading } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  if (!isLoginModalOpen) return null;

  const handleBackdropClick = () => {
    if (user) {
      setIsLoginModalOpen(false);
    }
  };

  const handleQuickAdmin = async () => {
    setError(null);
    try {
      await loginAsAdmin();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Đăng nhập nhanh thất bại.");
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await login(username, password);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Đăng nhập thất bại.");
    }
  };

  return (
    <div className="login-modal-backdrop" onClick={handleBackdropClick}>
      <div className="login-modal-card" onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="login-modal-header">
          <div>
            <h3 style={{ margin: 0, fontSize: "16px", fontWeight: 700 }}>
              Đăng nhập AI BI Assistant
            </h3>
          </div>
          {user && (
            <button
              onClick={() => setIsLoginModalOpen(false)}
              style={{
                background: "transparent",
                border: "none",
                color: "#FFFFFF",
                fontSize: "18px",
                cursor: "pointer",
                padding: "4px",
                lineHeight: 1,
              }}
              type="button"
              aria-label="Đóng"
            >
              ✕
            </button>
          )}
        </div>

        {/* Body */}
        <div className="login-modal-body">
          {error && <div className="login-error-box">{error}</div>}

          {/* Standard Login Form */}
          <form onSubmit={handleSubmit}>
            <div style={{ marginBottom: "12px" }}>
              <label
                style={{ display: "block", fontSize: "12px", fontWeight: 600, color: "#334155" }}
              >
                Tên đăng nhập
              </label>
              <input
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="ví dụ: admin..."
                required
                className="login-input"
              />
            </div>

            <div style={{ marginBottom: "14px" }}>
              <label
                style={{ display: "block", fontSize: "12px", fontWeight: 600, color: "#334155" }}
              >
                Mật khẩu
              </label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                required
                className="login-input"
              />
            </div>

            <button type="submit" disabled={loading} className="login-submit-btn">
              {loading ? "Đang xử lý..." : "Đăng nhập"}
            </button>
          </form>

          <div className="login-divider">Hoặc đăng nhập nhanh</div>

          {/* Quick Admin Login Button */}
          <button
            type="button"
            onClick={handleQuickAdmin}
            disabled={loading}
            className="login-gate-admin-btn"
            style={{ marginBottom: 0, justifyContent: "center", textAlign: "center" }}
            title="Đăng nhập ngay lập tức với tài khoản Admin toàn quyền"
          >
            <span style={{ fontSize: "14px", fontWeight: 700 }}>
              {loading ? "Đang xác thực Admin..." : "Đăng nhập nhanh Admin"}
            </span>
          </button>
        </div>
      </div>
    </div>
  );
}

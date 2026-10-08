"use client";

import React, { useEffect, useState } from "react";
import { useAuth } from "@/context/AuthContext";

export function LoginModal() {
  const { user, isLoginModalOpen, setIsLoginModalOpen, login, loginUsername, loading } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (isLoginModalOpen) {
      setUsername(loginUsername);
      setPassword("");
      setError(null);
    }
  }, [isLoginModalOpen, loginUsername]);

  if (!isLoginModalOpen) return null;

  const handleBackdropClick = () => {
    if (user) {
      setIsLoginModalOpen(false);
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
        </div>
      </div>
    </div>
  );
}

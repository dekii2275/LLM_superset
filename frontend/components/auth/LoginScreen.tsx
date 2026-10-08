"use client";

import React, { useState } from "react";
import Image from "next/image";
import { useAuth } from "@/context/AuthContext";

export function LoginScreen() {
  const { login, loginAsAdmin, loading } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  const handleQuickAdmin = async () => {
    setError(null);
    try {
      await loginAsAdmin();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Đăng nhập nhanh Admin thất bại.");
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await login(username, password);
    } catch (err: unknown) {
      setError(
        err instanceof Error
          ? err.message
          : "Đăng nhập thất bại. Vui lòng kiểm tra lại tài khoản hoặc mật khẩu.",
      );
    }
  };

  return (
    <div className="login-screen-wrap">
      <div className="login-screen-card">
        {/* Banner header */}
        <div className="login-screen-header">
          <div style={{ display: "flex", justifyContent: "center", marginBottom: "8px" }}>
            <Image
              src="/superset-logo-transparent.png"
              alt="Apache Superset"
              width={140}
              height={70}
              priority
              style={{ objectFit: "contain" }}
            />
          </div>
          <h2 style={{ margin: 0, fontSize: "20px", fontWeight: 700, color: "#FFFFFF" }}>
            AI BI Assistant
          </h2>
        </div>

        {/* Main login body */}
        <div className="login-screen-body">
          {error && <div className="login-error-box">{error}</div>}

          {/* Form đăng nhập */}
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

            <div style={{ marginBottom: "16px" }}>
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

            <button
              type="submit"
              disabled={loading}
              className="login-submit-btn"
              style={{ marginTop: 0 }}
            >
              {loading ? "Đang xử lý..." : "Đăng nhập"}
            </button>
          </form>

          <div className="login-divider">Hoặc đăng nhập nhanh</div>

          {/* Nút Đăng nhập nhanh Admin */}
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

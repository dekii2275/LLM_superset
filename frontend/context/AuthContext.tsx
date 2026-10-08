"use client";

import React, { createContext, useContext, useEffect, useState } from "react";
import type { UserProfile } from "@/lib/types";
import { setAuthToken, loginApi, getDemoUsersApi } from "@/lib/api";

type AuthContextType = {
  user: UserProfile | null;
  loading: boolean;
  demoUsers: UserProfile[];
  login: (username: string, password: string) => Promise<void>;
  loginAsAdmin: () => Promise<void>;
  logout: () => void;
  quickSwitchUser: (user: UserProfile) => Promise<void>;
  isLoginModalOpen: boolean;
  setIsLoginModalOpen: (open: boolean) => void;
};

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<UserProfile | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [demoUsers, setDemoUsers] = useState<UserProfile[]>([]);
  const [isLoginModalOpen, setIsLoginModalOpen] = useState<boolean>(false);

  useEffect(() => {
    async function initAuth() {
      try {
        const users = await getDemoUsersApi();
        setDemoUsers(users);

        // Luôn yêu cầu đăng nhập khi mới mở app hoặc reload (F5)
        setAuthToken(null);
        setUser(null);
      } catch (e) {
        console.warn("Auth initialization error:", e);
      } finally {
        setLoading(false);
      }
    }
    initAuth();
  }, []);

  const login = async (username: string, password: string) => {
    setLoading(true);
    try {
      const res = await loginApi(username, password);
      setAuthToken(res.token);
      setUser(res.user);
      setIsLoginModalOpen(false);
    } finally {
      setLoading(false);
    }
  };

  const loginAsAdmin = async () => {
    return login("admin", "admin123");
  };

  const logout = () => {
    setAuthToken(null);
    setUser(null);
    setIsLoginModalOpen(false);
  };

  const quickSwitchUser = async (targetUser: UserProfile) => {
    setLoading(true);
    try {
      const password = targetUser.username === "admin" ? "admin123" : "pass123";
      const res = await loginApi(targetUser.username, password);
      setAuthToken(res.token);
      setUser(res.user);
      setIsLoginModalOpen(false);
    } catch (e) {
      console.error("Quick switch failed:", e);
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        loading,
        demoUsers,
        login,
        loginAsAdmin,
        logout,
        quickSwitchUser,
        isLoginModalOpen,
        setIsLoginModalOpen,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}

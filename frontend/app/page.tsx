"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { AppHeader } from "@/components/layout/AppHeader";
import { Sidebar } from "@/components/layout/Sidebar";
import { ChatPanel } from "@/components/chat/ChatPanel";
import { VisualizationPanel } from "@/components/visualization/VisualizationPanel";
import { ApiError, askAI } from "@/lib/api";
import type { ChatMessage, CreateDashboardResult } from "@/lib/types";

export default function Home() {
  const [conversationTitle, setConversationTitle] = useState("New Analysis");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [embeddedDashboard, setEmbeddedDashboard] = useState<CreateDashboardResult | null>(null);
  const [dashboardRefresh, setDashboardRefresh] = useState(0);
  const [loadingLabel, setLoadingLabel] = useState("Analyzing your data…");
  const loadingRef = useRef(false);
  const requestIdRef = useRef(0);

  const handleNewAnalysis = useCallback(() => {
    requestIdRef.current += 1;
    setConversationTitle("New Analysis");
    setMessages([]);
    setInput("");
    setError(null);
    loadingRef.current = false;
    setLoading(false);
    setSidebarOpen(false);
    setEmbeddedDashboard(null);
    setDashboardRefresh(0);
  }, []);

  useEffect(() => {
    const handleShortcut = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        handleNewAnalysis();
      }
    };
    window.addEventListener("keydown", handleShortcut);
    return () => window.removeEventListener("keydown", handleShortcut);
  }, [handleNewAnalysis]);

  const handleSend = async (question: string) => {
    const trimmed = question.trim();
    if (!trimmed || loadingRef.current) return;

    const requestId = ++requestIdRef.current;
    loadingRef.current = true;
    setLoading(true);
    setInput("");
    setError(null);
    const lowered = trimmed.toLowerCase();
    setLoadingLabel(lowered.includes("dashboard") && /(create|tạo)/.test(lowered) ? "Preparing dashboard…" : lowered.includes("dashboard") ? "Preparing dashboard update…" : /(create|tạo|save|lưu).*?(chart|biểu đồ)/.test(lowered) ? "Preparing chart…" : /(change|rename|edit|đổi|sửa).*?(chart|biểu đồ)/.test(lowered) ? "Preparing chart update…" : "Analyzing your data…");
    setConversationTitle((current) => current === "New Analysis" ? trimmed.slice(0, 34) : current);

    const userMessage: ChatMessage = {
      id: `user-${Date.now()}`,
      role: "user",
      content: trimmed,
      createdAt: new Date().toISOString(),
    };
    setMessages((current) => [...current, userMessage]);

    try {
      const previousAssistant = [...messages].reverse().find(
        (item) => item.role === "assistant" && item.query && item.visualization,
      );
      const context = {
        ...(previousAssistant?.query && previousAssistant.visualization ? { last_query: previousAssistant.query, last_visualization: previousAssistant.visualization } : {}),
        ...(embeddedDashboard?.dashboard_id ? { active_dashboard_id: embeddedDashboard.dashboard_id, active_dashboard_title: embeddedDashboard.dashboard_name } : {}),
      };
      const response = await askAI(trimmed, context);
      if (requestId !== requestIdRef.current) return;
      const assistantMessage: ChatMessage = {
        id: `assistant-${Date.now()}`,
        role: "assistant",
        content: response.answer,
        createdAt: new Date().toISOString(),
        toolCalls: response.tool_calls,
        intent: response.intent,
        actionPlan: response.action_plan,
        dashboardPlan: response.dashboard_plan,
        pendingAction: response.pending_action,
        query: response.query,
        visualization: response.visualization,
      };
      setMessages((current) => [...current, assistantMessage]);
    } catch (requestError) {
      if (requestId === requestIdRef.current) {
        setError(requestError instanceof ApiError ? requestError.message : "Could not reach the AI service. Please try again.");
      }
    } finally {
      if (requestId === requestIdRef.current) {
        loadingRef.current = false;
        setLoading(false);
      }
    }
  };

  return (
    <div className={`app-frame ${sidebarOpen ? "sidebar-open" : ""}`}>
      <AppHeader sidebarOpen={sidebarOpen} onToggleSidebar={() => setSidebarOpen((open) => !open)} />
      <main className="workspace" id="main">
        <Sidebar onNewAnalysis={handleNewAnalysis} />
        {sidebarOpen && (
          <button
            className="mobile-sidebar-scrim"
            type="button"
            aria-label="Close navigation"
            onClick={() => setSidebarOpen(false)}
          />
        )}
        <ChatPanel
          title={conversationTitle}
          messages={messages}
          input={input}
          loading={loading}
          error={error}
          onInputChange={setInput}
          onSend={handleSend}
          onDashboardCreated={setEmbeddedDashboard}
          onDashboardUpdated={(result) => {
            if (result?.dashboard_id) setEmbeddedDashboard(result);
            setDashboardRefresh((value) => value + 1);
          }}
          loadingLabel={loadingLabel}
        />
        <VisualizationPanel
          dashboardId={embeddedDashboard?.dashboard_id ?? undefined}
          dashboardTitle={embeddedDashboard?.dashboard_name ?? undefined}
          refreshToken={dashboardRefresh}
        />
      </main>
    </div>
  );
}

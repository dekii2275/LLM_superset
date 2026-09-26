"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { AppLayout } from "@/components/layout/AppLayout";
import { ChatPanel } from "@/components/chat/ChatPanel";
import { ApiError, askAI, getAISettings } from "@/lib/api";
import type { ChatMessage, CreateDashboardResult } from "@/lib/types";

export default function Home() {
  const [conversationTitle, setConversationTitle] = useState("Phân tích mới");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [embeddedDashboard, setEmbeddedDashboard] = useState<CreateDashboardResult | null>(null);
  const [loadingLabel, setLoadingLabel] = useState("Đang phân tích dữ liệu…");
  const [llmEnabled, setLlmEnabled] = useState<boolean | null>(null);
  const loadingRef = useRef(false);
  const requestIdRef = useRef(0);

  useEffect(() => {
    let active = true;
    void getAISettings()
      .then((settings) => { if (active) setLlmEnabled(settings.llm_enabled); })
      .catch(() => { if (active) setLlmEnabled(false); });
    return () => { active = false; };
  }, []);

  const handleNewAnalysis = useCallback(() => {
    requestIdRef.current += 1;
    setConversationTitle("Phân tích mới");
    setMessages([]);
    setInput("");
    setError(null);
    loadingRef.current = false;
    setLoading(false);
    setEmbeddedDashboard(null);
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
    if (llmEnabled !== true) {
      setError("Hãy bật trò chuyện AI trong Cài đặt trước khi gửi câu hỏi.");
      return;
    }
    if (!trimmed || loadingRef.current) return;

    const requestId = ++requestIdRef.current;
    loadingRef.current = true;
    setLoading(true);
    setInput("");
    setError(null);
    const lowered = trimmed.toLowerCase();
    setLoadingLabel(lowered.includes("dashboard") && /(create|tạo)/.test(lowered) ? "Đang chuẩn bị bảng điều khiển…" : lowered.includes("dashboard") ? "Đang chuẩn bị cập nhật bảng điều khiển…" : /(create|tạo|save|lưu).*?(chart|biểu đồ)/.test(lowered) ? "Đang chuẩn bị biểu đồ…" : /(change|rename|edit|đổi|sửa).*?(chart|biểu đồ)/.test(lowered) ? "Đang chuẩn bị cập nhật biểu đồ…" : "Đang phân tích dữ liệu…");
    setConversationTitle((current) => current === "Phân tích mới" ? trimmed.slice(0, 34) : current);

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
        setError(requestError instanceof ApiError ? requestError.message : "Không thể kết nối với dịch vụ AI. Vui lòng thử lại.");
      }
    } finally {
      if (requestId === requestIdRef.current) {
        loadingRef.current = false;
        setLoading(false);
      }
    }
  };

  return (
    <AppLayout onNewAnalysis={handleNewAnalysis}>
      <ChatPanel
        title={conversationTitle}
        messages={messages}
        input={input}
        loading={loading}
        llmEnabled={llmEnabled}
        error={error}
        onInputChange={setInput}
        onSend={handleSend}
        onDashboardCreated={setEmbeddedDashboard}
        onDashboardUpdated={(result) => {
          if (result?.dashboard_id) setEmbeddedDashboard(result);
        }}
        loadingLabel={loadingLabel}
      />
    </AppLayout>
  );
}

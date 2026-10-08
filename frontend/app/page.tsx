"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { AppLayout } from "@/components/layout/AppLayout";
import { ChatPanel } from "@/components/chat/ChatPanel";
import {
  ApiError,
  askAI,
  createChatSession,
  deleteChatSession,
  getAISettings,
  getChatSessionMessages,
  getChatSessions,
} from "@/lib/api";
import type {
  AIActionPlan,
  ChatMessage,
  ChatSession,
  CreateDashboardResult,
  DashboardPlan,
  DbChatMessage,
  IntentInfo,
  QueryResult,
  VisualizationSpec,
} from "@/lib/types";

import { useDataset } from "@/context/DatasetContext";

function dbMessageToUiMessage(m: DbChatMessage): ChatMessage {
  const meta = (m.metadata || {}) as Record<string, unknown>;
  return {
    id: `db-msg-${m.id || Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    role: m.sender as "user" | "assistant",
    content: m.content,
    createdAt: m.created_at || new Date().toISOString(),
    query:
      (meta.query as QueryResult) ||
      (meta.sql ? { sql: meta.sql as string, columns: [], rows: [], row_count: 0 } : undefined),
    visualization: meta.visualization as VisualizationSpec | undefined,
    intent: meta.intent
      ? typeof meta.intent === "string"
        ? { type: meta.intent as any }
        : (meta.intent as IntentInfo)
      : undefined,
    dashboardPlan: meta.dashboard_plan as DashboardPlan | undefined,
    actionPlan: meta.action_plan as AIActionPlan | undefined,
    pendingAction: meta.pending_action as any,
    cached: Boolean(meta.cached),
    cache_type: (meta.cache_type as string) || undefined,
    cache_latency_ms: (meta.cache_latency_ms as number) || undefined,
    applied_rls_filter: (meta.applied_rls_filter as string) || undefined,
  };
}

export default function Home() {
  const { activeDataset, activeDatasetId, setActiveDatasetId } = useDataset();
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

  // Chat Session persistence state
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);

  // Load chat sessions from PostgreSQL
  const loadSessions = useCallback(async () => {
    try {
      const list = await getChatSessions(activeDatasetId || undefined);
      setSessions(list);
    } catch {
      // Ignore network errors
    }
  }, [activeDatasetId]);

  useEffect(() => {
    void loadSessions();
  }, [loadSessions]);

  useEffect(() => {
    if (activeDataset?.default_dashboard_id) {
      setEmbeddedDashboard({
        success: true,
        dashboard_id: activeDataset.default_dashboard_id,
        dashboard_name:
          activeDataset.default_dashboard_title || activeDataset.name || "Bảng điều khiển",
        chart_ids: [],
        url: "",
        message: "Sẵn sàng",
      });
    } else {
      setEmbeddedDashboard(null);
    }
  }, [activeDataset]);

  useEffect(() => {
    let active = true;
    void getAISettings()
      .then((settings) => {
        if (active) setLlmEnabled(settings.llm_enabled);
      })
      .catch(() => {
        if (active) setLlmEnabled(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const handleSelectDataset = useCallback(
    (datasetId: number) => {
      setActiveDatasetId(datasetId);
      setEmbeddedDashboard(null);
      setMessages([]);
      setError(null);
    },
    [setActiveDatasetId],
  );

  const handleNewAnalysis = useCallback(() => {
    requestIdRef.current += 1;
    setActiveSessionId(null);
    setConversationTitle("Phân tích mới");
    setMessages([]);
    setInput("");
    setError(null);
    loadingRef.current = false;
    setLoading(false);
    if (activeDataset?.default_dashboard_id) {
      setEmbeddedDashboard({
        success: true,
        dashboard_id: activeDataset.default_dashboard_id,
        dashboard_name:
          activeDataset.default_dashboard_title || activeDataset.name || "Bảng điều khiển",
        chart_ids: [],
        url: "",
        message: "Sẵn sàng",
      });
    } else {
      setEmbeddedDashboard(null);
    }
  }, [activeDataset]);

  // Select an existing chat session and restore messages
  const handleSelectSession = useCallback(
    async (sessionId: string) => {
      requestIdRef.current += 1;
      setActiveSessionId(sessionId);
      const matched = sessions.find((s) => s.id === sessionId);
      if (matched) {
        setConversationTitle(matched.title);
      }
      setLoading(true);
      setLoadingLabel("Đang tải lịch sử phiên hội thoại…");
      setError(null);
      try {
        const dbMsgs = await getChatSessionMessages(sessionId);
        setMessages(dbMsgs.map(dbMessageToUiMessage));
      } catch {
        setError("Không thể tải tin nhắn của phiên này.");
      } finally {
        setLoading(false);
      }
    },
    [sessions],
  );

  // Delete a chat session
  const handleDeleteSession = useCallback(
    async (sessionId: string) => {
      try {
        await deleteChatSession(sessionId);
        setSessions((prev) => prev.filter((s) => s.id !== sessionId));
        if (activeSessionId === sessionId) {
          handleNewAnalysis();
        }
      } catch {
        alert("Không thể xóa phiên hội thoại.");
      }
    },
    [activeSessionId, handleNewAnalysis],
  );

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
    setLoadingLabel(
      lowered.includes("dashboard") && /(create|tạo)/.test(lowered)
        ? "Đang chuẩn bị bảng điều khiển…"
        : lowered.includes("dashboard")
          ? "Đang chuẩn bị cập nhật bảng điều khiển…"
          : /(create|tạo|save|lưu).*?(chart|biểu đồ)/.test(lowered)
            ? "Đang chuẩn bị biểu đồ…"
            : /(change|rename|edit|đổi|sửa).*?(chart|biểu đồ)/.test(lowered)
              ? "Đang chuẩn bị cập nhật biểu đồ…"
              : "Đang phân tích dữ liệu…",
    );

    // Auto-create chat session if starting a new one
    let currentSessionId = activeSessionId;
    if (!currentSessionId) {
      const newTitle = trimmed.slice(0, 36);
      setConversationTitle(newTitle);
      try {
        const newSession = await createChatSession(newTitle, activeDatasetId);
        currentSessionId = newSession.id;
        setActiveSessionId(newSession.id);
        setSessions((prev) => [newSession, ...prev]);
      } catch {
        // Continue even if session creation fails
      }
    }

    const userMessage: ChatMessage = {
      id: `user-${Date.now()}`,
      role: "user",
      content: trimmed,
      createdAt: new Date().toISOString(),
    };
    setMessages((current) => [...current, userMessage]);

    try {
      const previousAssistant = [...messages]
        .reverse()
        .find((item) => item.role === "assistant" && item.query && item.query.sql);
      const isDashboardHeatmapFollowup =
        /heatmap|biểu đồ nhiệt|bieu do nhiet/i.test(trimmed) &&
        /thêm|phải có|cần có|bổ sung|thiếu|add|include/i.test(trimmed);
      const pendingDashboardMessage = isDashboardHeatmapFollowup
        ? [...messages]
            .reverse()
            .find(
              (item) =>
                item.role === "assistant" &&
                item.pendingAction?.action === "CREATE_DASHBOARD" &&
                item.dashboardPlan,
            )
        : undefined;
      // Multi-turn conversation history for context and filter accumulation (last 8 messages = 4 turns)
      const conversationHistory = messages.slice(-8).map((m) => ({
        role: m.role,
        content: m.content,
      }));

      const context = {
        ...(previousAssistant?.query
          ? {
              last_query: previousAssistant.query,
              last_visualization: previousAssistant.visualization,
            }
          : {}),
        ...(pendingDashboardMessage?.dashboardPlan
          ? { pending_dashboard_plan: pendingDashboardMessage.dashboardPlan }
          : {}),
        ...(embeddedDashboard?.dashboard_id
          ? {
              active_dashboard_id: embeddedDashboard.dashboard_id,
              active_dashboard_title: embeddedDashboard.dashboard_name,
            }
          : {}),
        ...(activeDatasetId ? { dataset_id: activeDatasetId } : {}),
        ...(currentSessionId ? { session_id: currentSessionId } : {}),
        conversation_history: conversationHistory,
      };

      const response = await askAI(trimmed, context, activeDatasetId, currentSessionId);
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
        cached: response.cached,
        cache_type: response.cache_type,
        cache_latency_ms: response.cache_latency_ms,
        applied_rls_filter: response.applied_rls_filter,
      };
      setMessages((current) => [...current, assistantMessage]);
    } catch (requestError) {
      if (requestId === requestIdRef.current) {
        setError(
          requestError instanceof ApiError
            ? requestError.message
            : "Không thể kết nối với dịch vụ AI. Vui lòng thử lại.",
        );
      }
    } finally {
      if (requestId === requestIdRef.current) {
        loadingRef.current = false;
        setLoading(false);
      }
    }
  };

  const currentDashboardId = activeDataset?.default_dashboard_id
    ? (embeddedDashboard?.dashboard_id ?? activeDataset.default_dashboard_id)
    : embeddedDashboard
      ? (embeddedDashboard.dashboard_id ?? undefined)
      : undefined;
  const currentDashboardTitle = activeDataset?.default_dashboard_id
    ? (embeddedDashboard?.dashboard_name ?? activeDataset.default_dashboard_title ?? undefined)
    : embeddedDashboard
      ? (embeddedDashboard.dashboard_name ?? undefined)
      : undefined;

  return (
    <AppLayout
      onNewAnalysis={handleNewAnalysis}
      activeDatasetId={activeDatasetId}
      onSelectDataset={handleSelectDataset}
      sessions={sessions}
      activeSessionId={activeSessionId}
      onSelectSession={handleSelectSession}
      onDeleteSession={handleDeleteSession}
    >
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
        dashboardId={currentDashboardId}
        dashboardTitle={currentDashboardTitle}
        activeDataset={activeDataset}
      />
    </AppLayout>
  );
}

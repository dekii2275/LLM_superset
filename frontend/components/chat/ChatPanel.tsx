import { useEffect, useRef } from "react";
import type {
  ChatMessage as ChatMessageType,
  CreateDashboardResult,
  DatasetSummary,
} from "@/lib/types";
import { ChatInput } from "./ChatInput";
import { ChatMessage } from "./ChatMessage";
import { EmbeddedDashboard } from "@/components/superset/EmbeddedDashboard";
import { SupersetPlaceholder } from "@/components/superset/SupersetPlaceholder";

type ChatPanelProps = {
  title: string;
  messages: ChatMessageType[];
  input: string;
  loading: boolean;
  llmEnabled: boolean | null;
  error: string | null;
  onInputChange: (value: string) => void;
  onSend: (question: string) => void;
  onDashboardCreated?: (result: CreateDashboardResult) => void;
  onDashboardUpdated?: (result?: CreateDashboardResult) => void;
  loadingLabel?: string;
  dashboardId?: number;
  dashboardTitle?: string;
  activeDataset?: DatasetSummary | null;
};

export function ChatPanel({
  title,
  messages,
  input,
  loading,
  llmEnabled,
  error,
  onInputChange,
  onSend,
  onDashboardCreated,
  onDashboardUpdated,
  loadingLabel = "Đang phân tích dữ liệu…",
  dashboardId,
  dashboardTitle,
  activeDataset,
}: ChatPanelProps) {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, loading]);

  return (
    <section className="chat-panel" aria-label="Cuộc trò chuyện">
      <div className={`chat-scroll-region ${messages.length === 0 ? "is-empty" : ""}`}>
        {messages.length === 0 ? (
          <div
            className="chat-dashboard"
            key={dashboardId ? `dash-${dashboardId}` : `ph-${activeDataset?.id || "none"}`}
          >
            {dashboardId ? (
              <EmbeddedDashboard
                key={dashboardId}
                variant="inline"
                dashboardId={dashboardId}
                title={dashboardTitle}
              />
            ) : (
              <SupersetPlaceholder
                dataset={activeDataset}
                onQuickAsk={(q) => {
                  onInputChange(q);
                  onSend(q);
                }}
              />
            )}
          </div>
        ) : (
          <div className="message-list" aria-live="polite">
            {messages.map((message, index) => (
              <ChatMessage
                key={message.id}
                message={message}
                dashboardDraftSuperseded={
                  message.pendingAction?.action === "CREATE_DASHBOARD" &&
                  messages
                    .slice(index + 1)
                    .some(
                      (later) =>
                        later.pendingAction?.action === "CREATE_DASHBOARD" &&
                        later.dashboardPlan?.title === message.dashboardPlan?.title,
                    )
                }
                onDashboardCreated={onDashboardCreated}
                onDashboardUpdated={onDashboardUpdated}
              />
            ))}
            {loading && (
              <div className="thinking-state" role="status" aria-live="polite">
                <span className="thinking-avatar">✦</span>
                <span>{loadingLabel}</span>
                <span className="thinking-dots">
                  <i />
                  <i />
                  <i />
                </span>
              </div>
            )}
            {error && (
              <p className="chat-error" role="alert">
                {error}
              </p>
            )}
            <div ref={endRef} />
          </div>
        )}
      </div>

      <ChatInput
        value={input}
        loading={loading}
        llmEnabled={llmEnabled}
        onChange={onInputChange}
        onSend={onSend}
      />
    </section>
  );
}

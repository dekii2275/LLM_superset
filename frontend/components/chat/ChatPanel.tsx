import { useEffect, useRef } from "react";
import type { ChatMessage as ChatMessageType, CreateDashboardResult } from "@/lib/types";
import { ChatInput } from "./ChatInput";
import { ChatMessage } from "./ChatMessage";
import { EmptyChat } from "./EmptyChat";

type ChatPanelProps = {
  title: string;
  messages: ChatMessageType[];
  input: string;
  loading: boolean;
  error: string | null;
  onInputChange: (value: string) => void;
  onSend: (question: string) => void;
  onDashboardCreated?: (result: CreateDashboardResult) => void;
  onDashboardUpdated?: (result?: CreateDashboardResult) => void;
  loadingLabel?: string;
};

export function ChatPanel({
  title,
  messages,
  input,
  loading,
  error,
  onInputChange,
  onSend,
  onDashboardCreated,
  onDashboardUpdated,
  loadingLabel = "Analyzing your data…",
}: ChatPanelProps) {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, loading]);

  return (
    <section className="chat-panel" aria-label="Conversation">
      <div className="chat-toolbar">
        <div className="thread-context">
          <span className="thread-icon">✦</span>
          <div>
            <strong>{title}</strong>
            <span>Natural language analysis</span>
          </div>
        </div>
      </div>

      <div className={`chat-scroll-region ${messages.length === 0 ? "is-empty" : ""}`}>
        {messages.length === 0 ? (
          <EmptyChat onAsk={onSend} />
        ) : (
          <div className="message-list" aria-live="polite">
            {messages.map((message) => (
              <ChatMessage key={message.id} message={message} onDashboardCreated={onDashboardCreated} onDashboardUpdated={onDashboardUpdated} />
            ))}
            {loading && (
              <div className="thinking-state" role="status" aria-live="polite">
                <span className="thinking-avatar">✦</span>
                <span>{loadingLabel}</span>
                <span className="thinking-dots"><i /><i /><i /></span>
              </div>
            )}
            {error && <p className="chat-error" role="alert">{error}</p>}
            <div ref={endRef} />
          </div>
        )}
      </div>

      <ChatInput value={input} loading={loading} onChange={onInputChange} onSend={onSend} />
    </section>
  );
}

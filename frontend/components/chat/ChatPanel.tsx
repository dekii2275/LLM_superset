import { useEffect, useRef } from "react";
import type { AnalysisResponse, ChatMessage as ChatMessageType } from "@/lib/types";
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
  onViewSql: (analysis: AnalysisResponse) => void;
  onViewVisualization: (analysis: AnalysisResponse) => void;
};

export function ChatPanel({
  title,
  messages,
  input,
  loading,
  error,
  onInputChange,
  onSend,
  onViewSql,
  onViewVisualization,
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
        <span className="mock-mode-badge"><span className="status-dot demo" /> MOCK MODE</span>
      </div>

      <div className={`chat-scroll-region ${messages.length === 0 ? "is-empty" : ""}`}>
        {messages.length === 0 ? (
          <EmptyChat onAsk={onSend} />
        ) : (
          <div className="message-list" aria-live="polite">
            {messages.map((message) => (
              <ChatMessage
                key={message.id}
                message={message}
                onViewSql={onViewSql}
                onViewVisualization={onViewVisualization}
              />
            ))}
            {loading && (
              <div className="thinking-state" role="status" aria-live="polite">
                <span className="thinking-avatar">✦</span>
                <span>Analyzing your data</span>
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

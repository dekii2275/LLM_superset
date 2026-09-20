import type { AnalysisResponse, ChatMessage as ChatMessageType } from "@/lib/types";
import { Icon } from "@/components/ui/Icon";

type ChatMessageProps = {
  message: ChatMessageType;
  onViewSql: (analysis: AnalysisResponse) => void;
  onViewVisualization: (analysis: AnalysisResponse) => void;
};

function formatTime(value: string): string {
  return new Date(value).toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" });
}

export function ChatMessage({ message, onViewSql, onViewVisualization }: ChatMessageProps) {
  const isAssistant = message.role === "assistant";

  return (
    <article className={`chat-message ${isAssistant ? "assistant-message" : "user-message"}`}>
      <div className={`message-avatar ${isAssistant ? "assistant-avatar" : "user-avatar"}`} aria-hidden="true">
        {isAssistant ? <Icon name="sparkle" size={16} /> : "AN"}
      </div>
      <div className="message-content-wrap">
        <div className="message-heading">
          <strong>{isAssistant ? "AI BI Assistant" : "You"}</strong>
          <time dateTime={message.createdAt}>{formatTime(message.createdAt)}</time>
        </div>
        <div className="message-content">{message.content}</div>

        {message.analysis?.query && (
          <div className="query-meta" aria-label="Query metadata">
            <span className="query-success"><span className="status-dot connected" /> Query completed</span>
            <span><Icon name="clock" size={13} /> {message.analysis.query.executionTimeMs} ms</span>
            <span>{message.analysis.query.rowCount} rows</span>
          </div>
        )}

        {message.analysis && (message.analysis.query || message.analysis.visualization) && (
          <div className="message-actions">
            {message.analysis.query && (
              <button type="button" onClick={() => onViewSql(message.analysis!)}>
                <Icon name="code" size={14} /> View SQL
              </button>
            )}
            {message.analysis.visualization && (
              <button type="button" onClick={() => onViewVisualization(message.analysis!)}>
                <Icon name="chart" size={14} /> View visualization
              </button>
            )}
          </div>
        )}
      </div>
    </article>
  );
}

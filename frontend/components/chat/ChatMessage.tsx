import type { ChatMessage as ChatMessageType, CreateDashboardResult } from "@/lib/types";
import { Icon } from "@/components/ui/Icon";
import { DynamicChart } from "./DynamicChart";
import { QueryResultDetails } from "./QueryResultDetails";
import { ActionConfirmation, DashboardConfirmation, EditChartConfirmation, EditDashboardConfirmation } from "./ActionConfirmation";

type ChatMessageProps = {
  message: ChatMessageType;
  onDashboardCreated?: (result: CreateDashboardResult) => void;
  onDashboardUpdated?: (result?: CreateDashboardResult) => void;
};

function formatTime(value: string): string {
  return new Date(value).toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" });
}

function actionLabel(action: string): string {
  return action.replace(/_/g, " ").toLowerCase().replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function parameterText(parameters: Record<string, unknown> | undefined): string[] {
  if (!parameters) return [];
  return Object.entries(parameters)
    .filter(([key]) => key !== "request")
    .map(([key, value]) => `${key.replace(/_/g, " ")}: ${String(value)}`);
}

export function ChatMessage({ message, onDashboardCreated, onDashboardUpdated }: ChatMessageProps) {
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

        {isAssistant && message.actionPlan && (
          <section className="action-plan-card" aria-label="Planned BI action">
            <span className="action-plan-kicker">Action preview</span>
            <strong>{actionLabel(message.actionPlan.action)}</strong>
            <p>{message.actionPlan.description}</p>
            {message.actionPlan.target_name && (
              <span className="action-plan-target">
                {message.actionPlan.target_type ?? "target"}: {message.actionPlan.target_name}
              </span>
            )}
            {parameterText(message.actionPlan.parameters).map((value) => (
              <span className="action-plan-detail" key={value}>{value}</span>
            ))}
            <span className="action-plan-status">Ready for the next step — no changes made</span>
          </section>
        )}

        {isAssistant && message.query && !message.query.error && message.visualization && (
          <DynamicChart
            spec={message.visualization}
            rows={message.query.rows}
            eyebrow={message.pendingAction?.action === "EDIT_DASHBOARD" && message.pendingAction.edit_dashboard_plan.operation === "ADD_CHART" ? "Preview biểu đồ sẽ thêm vào dashboard" : undefined}
          />
        )}

        {isAssistant && message.query && !message.query.error && (
          <QueryResultDetails query={message.query} />
        )}

        {isAssistant && message.pendingAction?.action === "CREATE_CHART" && message.query && message.visualization && (
          <ActionConfirmation
            action={message.pendingAction}
            query={message.query}
            visualization={message.visualization}
          />
        )}

        {isAssistant && message.pendingAction?.action === "CREATE_DASHBOARD" && (
          <DashboardConfirmation action={message.pendingAction} onDashboardCreated={onDashboardCreated} />
        )}

        {isAssistant && message.pendingAction?.action === "EDIT_CHART" && (
          <EditChartConfirmation action={message.pendingAction} onUpdated={() => onDashboardUpdated?.()} />
        )}

        {isAssistant && message.pendingAction?.action === "EDIT_DASHBOARD" && (
          <EditDashboardConfirmation
            action={message.pendingAction}
            query={message.query}
            visualization={message.visualization}
            onUpdated={onDashboardUpdated}
          />
        )}

        {isAssistant && message.toolCalls && message.toolCalls.length > 0 && (
          <div className="query-meta" aria-label="Superset tools used">
            {message.toolCalls.map((toolCall, index) => (
              <span key={`${toolCall.tool}-${index}`} title={toolCall.summary ?? undefined}>
                <span className={`status-dot ${toolCall.status === "success" ? "connected" : "disconnected"}`} />
                {toolCall.tool.replace(/_/g, " ")}
              </span>
            ))}
          </div>
        )}
      </div>
    </article>
  );
}

import { useRef, useState } from "react";
import type { ChatMessage as ChatMessageType, CreateDashboardResult } from "@/lib/types";
import { Icon } from "@/components/ui/Icon";
import { DynamicChart } from "./DynamicChart";
import { QueryResultDetails } from "./QueryResultDetails";
import {
  ActionConfirmation,
  DashboardConfirmation,
  EditChartConfirmation,
  EditDashboardConfirmation,
} from "./ActionConfirmation";
import { ApiError, explainChart } from "@/lib/api";
import type { ChartExplanation } from "@/lib/types";

type ChatMessageProps = {
  message: ChatMessageType;
  dashboardDraftSuperseded?: boolean;
  onDashboardCreated?: (result: CreateDashboardResult) => void;
  onDashboardUpdated?: (result?: CreateDashboardResult) => void;
};

function formatTime(value: string): string {
  return new Date(value).toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" });
}

function actionLabel(action: string): string {
  const labels: Record<string, string> = {
    CREATE_CHART: "Tạo biểu đồ",
    CREATE_DASHBOARD: "Tạo bảng điều khiển",
    EDIT_CHART: "Chỉnh sửa biểu đồ",
    EDIT_DASHBOARD: "Chỉnh sửa bảng điều khiển",
  };
  return labels[action] ?? action.replace(/_/g, " ").toLowerCase();
}

function parameterText(parameters: Record<string, unknown> | undefined): string[] {
  if (!parameters) return [];
  const parameterLabels: Record<string, string> = {
    chart_type: "Loại biểu đồ",
    dashboard_id: "Mã bảng điều khiển",
    chart_id: "Mã biểu đồ",
  };
  return Object.entries(parameters)
    .filter(([key]) => key !== "request")
    .map(([key, value]) => `${parameterLabels[key] ?? key.replace(/_/g, " ")}: ${String(value)}`);
}

export function ChatMessage({
  message,
  dashboardDraftSuperseded,
  onDashboardCreated,
  onDashboardUpdated,
}: ChatMessageProps) {
  const isAssistant = message.role === "assistant";
  const [chartExplanation, setChartExplanation] = useState<ChartExplanation | null>(null);
  const [explanationOpen, setExplanationOpen] = useState(false);
  const [explanationLoading, setExplanationLoading] = useState(false);
  const [explanationError, setExplanationError] = useState<string | null>(null);
  const explanationLoadingRef = useRef(false);
  const query = message.query;
  const visualization = message.visualization;
  const canExplainChart = Boolean(
    isAssistant &&
      query &&
      !query.error &&
      query.sql &&
      query.rows.length >= 2 &&
      visualization &&
      visualization.type !== "none" &&
      ["bar", "line", "pie", "area"].includes(visualization.type) &&
      visualization.x_axis &&
      visualization.y_axis,
  );

  const handleChartExplanation = async () => {
    if (explanationLoadingRef.current) return;
    if (chartExplanation) {
      setExplanationOpen((open) => !open);
      return;
    }
    if (!query?.sql || !visualization) return;

    explanationLoadingRef.current = true;
    setExplanationLoading(true);
    setExplanationError(null);
    try {
      const result = await explainChart(query.sql, visualization);
      setChartExplanation(result);
      setExplanationOpen(true);
    } catch (requestError) {
      setExplanationError(
        requestError instanceof ApiError
          ? requestError.message
          : "Không thể giải thích biểu đồ. Vui lòng thử lại.",
      );
      setExplanationOpen(false);
    } finally {
      explanationLoadingRef.current = false;
      setExplanationLoading(false);
    }
  };

  return (
    <article className={`chat-message ${isAssistant ? "assistant-message" : "user-message"}`}>
      <div
        className={`message-avatar ${isAssistant ? "assistant-avatar" : "user-avatar"}`}
        aria-hidden="true"
      >
        {isAssistant ? <Icon name="sparkle" size={16} /> : "AN"}
      </div>
      <div className="message-content-wrap">
        <div className="message-heading">
          <div className="flex items-center gap-2 flex-wrap">
            <strong>{isAssistant ? "AI BI Assistant" : "Bạn"}</strong>
            {message.cached && (
              <span
                className="cache-hit-badge"
                title={`Phản hồi tức thì từ Semantic Cache (${message.cache_latency_ms ?? 12}ms)`}
              >
                ⚡ Cache ({message.cache_latency_ms ?? 12}ms)
              </span>
            )}
            {message.applied_rls_filter && (
              <span
                className="rls-badge"
                title={`Đã tiêm điều kiện phân quyền: ${message.applied_rls_filter}`}
              >
                🔒 {message.applied_rls_filter}
              </span>
            )}
          </div>
          <time dateTime={message.createdAt}>{formatTime(message.createdAt)}</time>
        </div>
        <div className="message-content">{message.content}</div>

        {isAssistant && message.actionPlan && (
          <section className="action-plan-card" aria-label="Thao tác BI đã lên kế hoạch">
            <span className="action-plan-kicker">Xem trước thao tác</span>
            <strong>{actionLabel(message.actionPlan.action)}</strong>
            <p>{message.actionPlan.description}</p>
            {message.actionPlan.target_name && (
              <span className="action-plan-target">
                {message.actionPlan.target_type ?? "Mục tiêu"}: {message.actionPlan.target_name}
              </span>
            )}
            {parameterText(message.actionPlan.parameters).map((value) => (
              <span className="action-plan-detail" key={value}>
                {value}
              </span>
            ))}
            <span className="action-plan-status">
              Sẵn sàng cho bước tiếp theo — chưa có thay đổi nào
            </span>
          </section>
        )}

        {isAssistant && message.query && !message.query.error && message.visualization && (
          <DynamicChart
            spec={message.visualization}
            rows={message.query.rows}
            eyebrow={
              message.pendingAction?.action === "EDIT_DASHBOARD" &&
              message.pendingAction.edit_dashboard_plan.operation === "ADD_CHART"
                ? "Xem trước biểu đồ sẽ thêm vào bảng điều khiển"
                : undefined
            }
          />
        )}

        {canExplainChart && (
          <section className="chart-explanation" aria-label="Giải thích biểu đồ">
            <button
              className="chart-explanation-trigger"
              type="button"
              onClick={handleChartExplanation}
              disabled={explanationLoading}
              aria-busy={explanationLoading}
              aria-expanded={explanationOpen}
            >
              <span aria-hidden="true">✦</span>
              {explanationLoading
                ? "Đang phân tích biểu đồ…"
                : chartExplanation
                  ? explanationOpen
                    ? "Ẩn giải thích"
                    : "Hiện giải thích"
                  : explanationError
                    ? "Thử lại"
                    : "Giải thích biểu đồ"}
            </button>
            {explanationError && (
              <p className="chart-explanation-error" role="alert">
                {explanationError}
              </p>
            )}
            {explanationOpen && chartExplanation && (
              <div className="chart-explanation-result" aria-live="polite">
                <div>
                  <h5>Tóm tắt</h5>
                  <p>{chartExplanation.summary}</p>
                </div>
                {chartExplanation.highlights.length > 0 && (
                  <div>
                    <h5>Điểm nổi bật</h5>
                    <ul>
                      {chartExplanation.highlights.map((highlight, index) => (
                        <li key={`${index}-${highlight}`}>{highlight}</li>
                      ))}
                    </ul>
                  </div>
                )}
                <div>
                  <h5>Lưu ý</h5>
                  <p>{chartExplanation.note}</p>
                </div>
              </div>
            )}
          </section>
        )}

        {isAssistant && message.query && !message.query.error && (
          <QueryResultDetails query={message.query} />
        )}

        {isAssistant &&
          message.pendingAction?.action === "CREATE_CHART" &&
          message.query &&
          message.visualization && (
            <ActionConfirmation
              action={message.pendingAction}
              query={message.query}
              visualization={message.visualization}
            />
          )}

        {isAssistant &&
          message.pendingAction?.action === "CREATE_DASHBOARD" &&
          dashboardDraftSuperseded && (
            <p className="action-cancelled">Bản nháp này đã được thay bằng bản mới ở phía dưới.</p>
          )}

        {isAssistant &&
          message.pendingAction?.action === "CREATE_DASHBOARD" &&
          !dashboardDraftSuperseded && (
            <DashboardConfirmation
              action={message.pendingAction}
              onDashboardCreated={onDashboardCreated}
            />
          )}

        {isAssistant && message.pendingAction?.action === "EDIT_CHART" && (
          <EditChartConfirmation
            action={message.pendingAction}
            onUpdated={() => onDashboardUpdated?.()}
          />
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
          <div className="query-meta" aria-label="Công cụ Superset đã dùng">
            {message.toolCalls.map((toolCall, index) => (
              <span key={`${toolCall.tool}-${index}`} title={toolCall.summary ?? undefined}>
                <span
                  className={`status-dot ${toolCall.status === "success" ? "connected" : "disconnected"}`}
                />
                {toolCall.tool.replace(/_/g, " ")}
              </span>
            ))}
          </div>
        )}
      </div>
    </article>
  );
}

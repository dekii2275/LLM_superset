type DashboardReportRequest = {
  dashboard_id?: number;
  active_tabs: string[];
  data_mask: Record<string, unknown>;
};

export function createDashboardReportRequest(
  dashboardId: number | undefined,
  activeTabs: unknown,
  dataMask: unknown,
): DashboardReportRequest {
  if (!Array.isArray(activeTabs)) {
    throw new Error("Không đọc được tab đang chọn. Hãy tải lại dashboard.");
  }
  // Superset can include undefined for an empty TABS container; JSON turns it into null.
  const tabs = activeTabs.filter((tab) => tab != null && tab !== "");
  if (tabs.some((tab) => typeof tab !== "string")) {
    throw new Error("Không đọc được tab đang chọn. Hãy tải lại dashboard.");
  }
  if (!dataMask || typeof dataMask !== "object" || Array.isArray(dataMask)) {
    throw new Error("Không đọc được bộ lọc đang chọn. Hãy tải lại dashboard.");
  }
  return {
    dashboard_id: dashboardId,
    active_tabs: [...new Set(tabs as string[])],
    data_mask: dataMask as Record<string, unknown>,
  };
}

export function supersetErrorMessage(payload: unknown, status: number): string {
  const detail =
    payload && typeof payload === "object" && "detail" in payload ? payload.detail : null;
  let message: string | undefined;
  if (typeof detail === "string") {
    message = detail;
  } else if (Array.isArray(detail)) {
    message = detail
      .filter((item) => item && typeof item.msg === "string")
      .map((item) => {
        const location = Array.isArray(item.loc) ? item.loc.join(".") : "";
        return `${location ? `${location}: ` : ""}${item.msg}`;
      })
      .join("; ");
  } else if (detail && typeof detail === "object" && "message" in detail) {
    message = typeof detail.message === "string" ? detail.message : undefined;
  }
  if (!message && status === 504) {
    message = "Tạo báo cáo mất quá lâu. Hãy thử lại sau hoặc chọn tab có ít biểu đồ hơn.";
  }
  return `${message || "Không thể kết nối với Superset."} (HTTP ${status})`;
}

import { Document, HeadingLevel, ImageRun, Packer, Paragraph } from "docx";

export type DashboardReport = {
  dashboard_title: string;
  active_tab_title: string;
  applied_filters: string[];
  generated_at: string;
  analysis: {
    overview: string;
    highlights: string[];
    chart_insights: { chart_id: number; insight: string }[];
  };
  charts: {
    id: number;
    title: string;
    screenshot_base64: string;
    rows: Record<string, unknown>[];
    row_count: number;
    truncated: boolean;
    unavailable: boolean;
  }[];
};

function chartImage(base64: string): Paragraph {
  const bytes = Uint8Array.from(atob(base64), (character) => character.charCodeAt(0));
  const dimensions = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const originalWidth = dimensions.getUint32(16);
  const originalHeight = dimensions.getUint32(20);
  const scale = Math.min(1, 600 / originalWidth, 680 / originalHeight);

  return new Paragraph({
    children: [
      new ImageRun({
        type: "png",
        data: bytes,
        transformation: {
          width: Math.round(originalWidth * scale),
          height: Math.round(originalHeight * scale),
        },
      }),
    ],
  });
}

export async function createDocxReport(report: DashboardReport): Promise<Blob> {
  const children: Paragraph[] = [
    new Paragraph({ text: report.dashboard_title, heading: HeadingLevel.TITLE }),
    new Paragraph({ text: "Báo cáo phân tích dashboard", heading: HeadingLevel.HEADING_1 }),
    new Paragraph({ text: `Tạo lúc ${new Date(report.generated_at).toLocaleString("vi-VN")}` }),
    new Paragraph({ text: `Tab: ${report.active_tab_title || "Dashboard"}` }),
    new Paragraph({
      text:
        report.applied_filters.length > 0
          ? `Bộ lọc đang chọn: ${report.applied_filters.join("; ")}`
          : "Không có bộ lọc đang chọn.",
    }),
    new Paragraph({ text: "Tổng quan", heading: HeadingLevel.HEADING_2 }),
    new Paragraph(report.analysis.overview),
  ];

  for (const highlight of report.analysis.highlights) {
    children.push(new Paragraph({ text: highlight, bullet: { level: 0 } }));
  }

  for (const chart of report.charts) {
    const insight = report.analysis.chart_insights.find((item) => item.chart_id === chart.id);
    children.push(new Paragraph({ text: chart.title, heading: HeadingLevel.HEADING_2 }));
    children.push(new Paragraph(insight?.insight ?? "Chưa có nhận xét riêng cho biểu đồ này."));
    if (chart.screenshot_base64) children.push(chartImage(chart.screenshot_base64));

    if (chart.unavailable) {
      children.push(new Paragraph("Không lấy được dữ liệu biểu đồ."));
    }

    if (chart.truncated) {
      children.push(
        new Paragraph(
          `Biểu đồ hiển thị ${chart.rows.length} dòng mẫu trên tổng số ${chart.row_count} dòng.`,
        ),
      );
    }
  }

  const document = new Document({
    creator: "AI BI Assistant",
    title: report.dashboard_title,
    sections: [{ children }],
  });
  return Packer.toBlob(document);
}

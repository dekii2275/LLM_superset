import { jsPDF } from "jspdf";
import type { DashboardReport } from "./docxReport";

export type ReportFonts = { regular: string; bold: string };
const MARGIN = 42;
const INK = "#172B3A";
const MUTED = "#5B6B78";
const GREEN = "#087F63";

async function loadReportFonts(): Promise<ReportFonts> {
  const load = async (name: string) => {
    const response = await fetch(`/fonts/NotoSans-${name}.ttf`);
    if (!response.ok) throw new Error("Không tải được font báo cáo. Hãy tải lại trang.");
    const bytes = new Uint8Array(await response.arrayBuffer());
    let binary = "";
    for (let offset = 0; offset < bytes.length; offset += 8192) {
      binary += String.fromCharCode(...bytes.subarray(offset, offset + 8192));
    }
    return btoa(binary);
  };
  const [regular, bold] = await Promise.all([load("Regular"), load("Bold")]);
  return { regular, bold };
}

// Lay out text and complete images directly in PDF coordinates. Never slice a chart bitmap.
export function buildPdfReport(report: DashboardReport, fonts: ReportFonts): jsPDF {
  const pdf = new jsPDF({ unit: "pt", format: "a4", compress: true, putOnlyUsedFonts: true });
  pdf.addFileToVFS("NotoSans-Regular.ttf", fonts.regular);
  pdf.addFileToVFS("NotoSans-Bold.ttf", fonts.bold);
  pdf.addFont("NotoSans-Regular.ttf", "NotoSans", "normal");
  pdf.addFont("NotoSans-Bold.ttf", "NotoSans", "bold");
  pdf.setProperties({ title: report.dashboard_title, author: "AI BI Assistant" });
  const width = pdf.internal.pageSize.getWidth();
  const height = pdf.internal.pageSize.getHeight();
  const contentWidth = width - MARGIN * 2;
  const bottom = height - 58;
  let y = 76;
  const style = (size: number, bold = false, color = INK) => {
    pdf.setFont("NotoSans", bold ? "bold" : "normal");
    pdf.setFontSize(size);
    pdf.setTextColor(color);
  };
  const wrap = (text: string, size = 10.5, bold = false, lineWidth = contentWidth): string[] => {
    style(size, bold);
    return pdf.splitTextToSize(text, lineWidth) as string[];
  };
  const header = () => {
    pdf.setFillColor(GREEN);
    pdf.rect(0, 0, width, 6, "F");
    style(9, true, GREEN);
    pdf.text("AI BI ASSISTANT", MARGIN, 32);
    style(8, false, MUTED);
    pdf.text("BÁO CÁO PHÂN TÍCH", width - MARGIN, 32, { align: "right" });
    pdf.setDrawColor("#DDE5E9");
    pdf.line(MARGIN, 46, width - MARGIN, 46);
  };
  const nextPage = () => {
    pdf.addPage();
    header();
    y = 76;
  };
  const ensure = (space: number) => {
    if (y + space > bottom) nextPage();
  };
  const paragraph = (text: string, size = 10.5, color = INK, indent = 0) => {
    const lines = wrap(text, size, false, contentWidth - indent);
    const leading = size * 1.55;
    for (const line of lines) {
      ensure(leading);
      style(size, false, color);
      pdf.text(line, MARGIN + indent, y);
      y += leading;
    }
    y += 10;
  };
  const sectionTitle = (title: string) => {
    ensure(45);
    style(15, true);
    pdf.text(title, MARGIN, y);
    y += 27;
  };
  header();
  style(9, true, GREEN);
  pdf.text("TỔNG QUAN DASHBOARD", MARGIN, y);
  y += 31;
  for (const line of wrap(report.dashboard_title, 24, true)) {
    ensure(32);
    style(24, true);
    pdf.text(line, MARGIN, y);
    y += 32;
  }
  y += 8;
  paragraph(`Tạo lúc ${new Date(report.generated_at).toLocaleString("vi-VN")}`, 9, MUTED);
  const context = [
    `Tab: ${report.active_tab_title || "Dashboard"}  |  ${report.charts.length} biểu đồ`,
    report.applied_filters.length
      ? `Bộ lọc: ${report.applied_filters.join("; ")}`
      : "Không có bộ lọc đang chọn.",
  ];
  for (const text of context) paragraph(text, 9, MUTED);
  y += 10;
  sectionTitle("Tổng quan");
  paragraph(report.analysis.overview);
  if (report.analysis.highlights.length) {
    y += 8;
    sectionTitle("Điểm nổi bật");
    report.analysis.highlights.forEach((text, index) => {
      ensure(34);
      style(10, true, GREEN);
      pdf.text(String(index + 1).padStart(2, "0"), MARGIN, y);
      paragraph(text, 10.5, INK, 28);
    });
  }

  if (report.charts.length) nextPage();
  report.charts.forEach((chart, index) => {
    const titleLines = wrap(chart.title, 14, true, contentWidth - 34);
    const insight = report.analysis.chart_insights.find((item) => item.chart_id === chart.id);
    const insightText = insight?.insight ?? "Chưa có nhận xét riêng cho biểu đồ này.";
    const insightLines = wrap(insightText);
    let image: { width: number; height: number } | undefined;
    if (chart.screenshot_base64) {
      const properties = pdf.getImageProperties(`data:image/png;base64,${chart.screenshot_base64}`);
      const scale = Math.min((contentWidth - 20) / properties.width, 350 / properties.height);
      image = { width: properties.width * scale, height: properties.height * scale };
    }
    const titleHeight = titleLines.length * 20 + 12;
    const imageHeight = image ? image.height + 24 : 0;
    const noteHeight = (chart.unavailable ? 25 : 0) + (chart.truncated ? 40 : 0);
    const blockHeight =
      titleHeight + imageHeight + 26 + insightLines.length * 16.275 + noteHeight + 24;
    // Ordinary chart sections stay together. Very long commentary flows onto continuation pages.
    ensure(Math.min(blockHeight, bottom - 76));
    style(10, true, GREEN);
    pdf.text(String(index + 1).padStart(2, "0"), MARGIN, y);
    for (const line of titleLines) {
      style(14, true);
      pdf.text(line, MARGIN + 34, y);
      y += 20;
    }
    y += 10;
    if (image) {
      pdf.setDrawColor("#DDE5E9");
      pdf.setFillColor("#FFFFFF");
      pdf.roundedRect(MARGIN, y, contentWidth, image.height + 20, 6, 6, "FD");
      pdf.addImage(
        `data:image/png;base64,${chart.screenshot_base64}`,
        "PNG",
        MARGIN + (contentWidth - image.width) / 2,
        y + 10,
        image.width,
        image.height,
      );
      y += imageHeight + 9;
    }
    ensure(32);
    style(8, true, GREEN);
    pdf.text("NHẬN XÉT", MARGIN, y);
    y += 19;
    paragraph(insightText);
    if (chart.unavailable) paragraph("Không lấy được dữ liệu biểu đồ.", 9, MUTED);
    if (chart.truncated) {
      paragraph(
        `Phân tích dựa trên ${chart.rows.length} dòng mẫu / ${chart.row_count} dòng dữ liệu.`,
        9,
        MUTED,
      );
    }
    y += 14;
  });
  const totalPages = pdf.getNumberOfPages();
  for (let page = 1; page <= totalPages; page++) {
    pdf.setPage(page);
    pdf.setDrawColor("#DDE5E9");
    pdf.line(MARGIN, height - 42, width - MARGIN, height - 42);
    style(8, false, MUTED);
    const tab = wrap(report.active_tab_title || "Dashboard", 8, false, contentWidth - 100)[0];
    pdf.text(tab, MARGIN, height - 26);
    pdf.text(`${page} / ${totalPages}`, width - MARGIN, height - 26, { align: "right" });
  }
  return pdf;
}

export async function createPdfReport(report: DashboardReport): Promise<Blob> {
  return buildPdfReport(report, await loadReportFonts()).output("blob");
}

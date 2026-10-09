import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { buildPdfReport } from "./pdfReport.ts";

const fonts = {
  regular: readFileSync(new URL("../public/fonts/NotoSans-Regular.ttf", import.meta.url)).toString(
    "base64",
  ),
  bold: readFileSync(new URL("../public/fonts/NotoSans-Bold.ttf", import.meta.url)).toString(
    "base64",
  ),
};
const png =
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4z8AAAAMBAQDJ/pLvAAAAAElFTkSuQmCC";
function report(count = 3, insight = "Biểu đồ giữ nguyên trên một trang.") {
  return {
    dashboard_title: "Báo cáo chuyến taxi tại New York",
    active_tab_title: "Trips & Revenue",
    applied_filters: ["Vendor Name: VeriFone Inc"],
    generated_at: "2026-10-09T02:00:00Z",
    analysis: {
      overview: "Tổng quan hoạt động và doanh thu.",
      highlights: ["Có 30.000 chuyến."],
      chart_insights: Array.from({ length: count }, (_, id) => ({ chart_id: id, insight })),
    },
    charts: Array.from({ length: count }, (_, id) => ({
      id,
      title: `Biểu đồ ${id + 1}`,
      screenshot_base64: png,
      rows: [],
      row_count: 0,
      truncated: false,
      unavailable: false,
    })),
  };
}
function pageStreams(pdf) {
  return pdf.internal.pages.slice(1).map((page) => page.join("\n"));
}

test("keeps every chart as one complete image within A4 content margins", () => {
  const pdf = buildPdfReport(report(), fonts);
  const pages = pageStreams(pdf);
  assert.doesNotMatch(pages[0], /\/I\d+ Do/, "overview is its own page");
  const images = pages.flatMap((page) => [
    ...page.matchAll(/([\d.]+) 0 0 ([\d.]+) ([\d.]+) ([\d.]+) cm\s+\/I\d+ Do/g),
  ]);
  assert.equal(images.length, 3, "each source image is drawn exactly once without strips");
  for (const image of images) {
    const [width, height, left, bottom] = image.slice(1).map(Number);
    assert.ok(left >= 42 && left + width <= 554, "image fits horizontal margins");
    assert.ok(bottom >= 58 && bottom + height <= 766, "image fits vertical margins");
  }
  assert.ok(pdf.getNumberOfPages() >= 4);
  assert.ok(pdf.output("arraybuffer").byteLength > 1000);
});

test("paginates long commentary without losing charts or overflowing the text area", () => {
  const pdf = buildPdfReport(
    report(2, "Nhận xét chi tiết về doanh thu và số chuyến. ".repeat(180)),
    fonts,
  );
  const pages = pageStreams(pdf);
  assert.ok(pages.length > 4, "long commentary continues on extra pages");
  assert.equal(
    pages.reduce((sum, page) => sum + [...page.matchAll(/\/I\d+ Do/g)].length, 0),
    2,
  );
  for (const page of pages) {
    for (const match of page.matchAll(/([\d.]+) ([\d.]+) Td/g)) {
      const y = Number(match[2]);
      assert.ok(y >= 24 && y <= 817, "all text stays within the page");
    }
  }
});

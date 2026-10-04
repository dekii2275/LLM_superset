import assert from "node:assert/strict";
import { test } from "node:test";
import JSZip from "jszip";
import { createDocxReport } from "./docxReport.ts";

test("places each chart image beside its own insight without a dashboard snapshot", async () => {
  const chartOnePng = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4z8AAAAMBAQDJ/pLvAAAAAElFTkSuQmCC";
  const chartTwoPng = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGNgYPgPAAEDAQAIicLsAAAAAElFTkSuQmCC";
  const report = {
    dashboard_title: "Báo cáo thử",
    active_tab_title: "Trips & Revenue",
    applied_filters: ["Vendor Name: Yellow"],
    generated_at: "2026-10-04T00:00:00.000Z",
    analysis: {
      overview: "Lượt đi tăng trong tuần.",
      highlights: ["Thứ Sáu có nhiều chuyến nhất."],
      chart_insights: [{ chart_id: 7, insight: "Biểu đồ thử nghiệm." }],
    },
    charts: [
      {
        id: 7,
        title: "Số chuyến theo ngày",
        screenshot_base64: chartOnePng,
        rows: [],
        row_count: 0,
        truncated: false,
        unavailable: false,
      },
      {
        id: 8,
        title: "Doanh thu theo ngày",
        screenshot_base64: chartTwoPng,
        rows: [],
        row_count: 0,
        truncated: false,
        unavailable: false,
      },
    ],
  };
  const blob = await createDocxReport(report);

  assert.equal(blob.type, "application/vnd.openxmlformats-officedocument.wordprocessingml.document");
  const archive = await JSZip.loadAsync(await blob.arrayBuffer());
  const documentXml = await archive.file("word/document.xml")!.async("string");
  const imageParts = Object.keys(archive.files).filter((path) =>
    path.startsWith("word/media/") && !archive.files[path].dir,
  );

  assert.equal(imageParts.length, 2, "DOCX should contain one image for each chart");
  const firstChart = documentXml.indexOf("Số chuyến theo ngày");
  const firstInsight = documentXml.indexOf("Biểu đồ thử nghiệm.");
  const secondChart = documentXml.indexOf("Doanh thu theo ngày");
  const firstImage = documentXml.indexOf("<w:drawing>", firstInsight);
  const secondImage = documentXml.indexOf("<w:drawing>", secondChart);
  assert.ok(firstChart < firstInsight && firstInsight < firstImage && firstImage < secondChart);
  assert.ok(secondChart < secondImage, "the second chart image should follow the second chart heading");
  assert.ok(!documentXml.includes("Dashboard hiện tại"), "report should not insert a full dashboard snapshot");
});

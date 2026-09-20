import type { AnalysisFilter, AnalysisTopic, ChartDatum, DemoConversation } from "./types";

export const SUGGESTED_QUESTIONS = [
  "Tổng doanh thu năm 2026?",
  "Xu hướng doanh thu theo tháng?",
  "Top 5 sản phẩm doanh thu cao nhất?",
  "Doanh thu theo thành phố?",
] as const;

export const MOCK_CONVERSATIONS: DemoConversation[] = [
  {
    id: "revenue-overview",
    title: "Revenue Overview",
    turns: [{ question: SUGGESTED_QUESTIONS[0], topic: "revenue-total" }],
  },
  {
    id: "top-products",
    title: "Top Products",
    turns: [{ question: SUGGESTED_QUESTIONS[2], topic: "top-products" }],
  },
  {
    id: "monthly-trend",
    title: "Monthly Trend",
    turns: [{ question: SUGGESTED_QUESTIONS[1], topic: "monthly-trend" }],
  },
  {
    id: "hanoi-analysis",
    title: "Hanoi Analysis",
    turns: [
      { question: SUGGESTED_QUESTIONS[2], topic: "top-products" },
      {
        question: "Chỉ xem ở Hà Nội.",
        topic: "top-products",
        filters: [{ field: "city", operator: "=", value: "Hà Nội", label: "City" }],
      },
    ],
  },
];

export const MONTHLY_REVENUE: ChartDatum[] = [
  { label: "Jan", value: 0.72 },
  { label: "Feb", value: 0.78 },
  { label: "Mar", value: 0.86 },
  { label: "Apr", value: 0.91 },
  { label: "May", value: 1.03 },
  { label: "Jun", value: 1.14 },
  { label: "Jul", value: 1.2 },
  { label: "Aug", value: 1.36 },
  { label: "Sep", value: 1.27 },
  { label: "Oct", value: 1.19 },
  { label: "Nov", value: 1.07 },
  { label: "Dec", value: 0.95 },
];

export const TOP_PRODUCTS: ChartDatum[] = [
  { label: "Laptop Pro", value: 2.5 },
  { label: "Smartphone X", value: 2.1 },
  { label: "Monitor Ultra", value: 1.8 },
  { label: "Tablet Air", value: 1.4 },
  { label: "Headphones Max", value: 1.1 },
];

export const HANOI_TOP_PRODUCTS: ChartDatum[] = [
  { label: "Laptop Pro", value: 1.28 },
  { label: "Smartphone X", value: 1.12 },
  { label: "Monitor Ultra", value: 0.93 },
  { label: "Tablet Air", value: 0.76 },
  { label: "Headphones Max", value: 0.61 },
];

export const CITY_REVENUE: ChartDatum[] = [
  { label: "Hà Nội", value: 4.82 },
  { label: "TP.HCM", value: 4.36 },
  { label: "Đà Nẵng", value: 1.42 },
  { label: "Hải Phòng", value: 1.08 },
  { label: "Cần Thơ", value: 0.8 },
];

export const HANOI_FILTER: AnalysisFilter = {
  field: "city",
  operator: "=",
  value: "Hà Nội",
  label: "City",
};

export const TOPIC_TITLES: Record<AnalysisTopic, string> = {
  "revenue-total": "Total Revenue · 2026",
  "monthly-trend": "Monthly Revenue Trend",
  "top-products": "Top 5 Products by Revenue",
  "city-revenue": "Revenue by City",
};

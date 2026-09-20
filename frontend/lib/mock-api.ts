import {
  CITY_REVENUE,
  HANOI_FILTER,
  HANOI_TOP_PRODUCTS,
  MOCK_CONVERSATIONS,
  MONTHLY_REVENUE,
  TOP_PRODUCTS,
  TOPIC_TITLES,
} from "./mock-data";
import type {
  AnalysisFilter,
  AnalysisResponse,
  AnalysisTopic,
  ChatMessage,
  DemoConversation,
} from "./types";

export type ConversationContext = {
  currentAnalysis?: AnalysisResponse;
};

const TOP_PRODUCTS_SQL = `SELECT
    product_name,
    SUM(revenue) AS total_revenue
FROM sales
GROUP BY product_name
ORDER BY total_revenue DESC
LIMIT 5;`;

function buildAnalysis(
  topic: AnalysisTopic,
  filters: AnalysisFilter[] = [],
  answerOverride?: string,
): AnalysisResponse {
  const isHanoiProducts =
    topic === "top-products" && filters.some((filter) => filter.field === HANOI_FILTER.field);

  switch (topic) {
    case "revenue-total":
      return {
        topic,
        answer: answerOverride ?? "Tổng doanh thu năm 2026 là 12.48 tỷ VNĐ.",
        query: {
          sql: `SELECT SUM(revenue) AS total_revenue
FROM sales
WHERE EXTRACT(YEAR FROM order_date) = 2026;`,
          executionTimeMs: 86,
          rowCount: 1,
          status: "success",
        },
        visualization: {
          type: "big_number",
          title: TOPIC_TITLES[topic],
          value: 12.48,
          formattedValue: "12.48 tỷ VNĐ",
        },
        filters,
      };

    case "monthly-trend":
      return {
        topic,
        answer: answerOverride ?? "Doanh thu tăng dần trong nửa đầu năm và đạt đỉnh vào tháng 8.",
        query: {
          sql: `SELECT
    DATE_TRUNC('month', order_date) AS month,
    SUM(revenue) AS monthly_revenue
FROM sales
WHERE EXTRACT(YEAR FROM order_date) = 2026
GROUP BY month
ORDER BY month;`,
          executionTimeMs: 112,
          rowCount: 12,
          status: "success",
        },
        visualization: {
          type: "line",
          title: TOPIC_TITLES[topic],
          data: MONTHLY_REVENUE,
          unit: "tỷ VNĐ",
        },
        filters,
      };

    case "top-products":
      return {
        topic,
        answer:
          answerOverride ??
          (isHanoiProducts
            ? "Đã áp dụng bộ lọc City = Hà Nội cho phân tích hiện tại."
            : "Đây là 5 sản phẩm có doanh thu cao nhất."),
        query: {
          sql: isHanoiProducts
            ? `SELECT
    product_name,
    SUM(revenue) AS total_revenue
FROM sales
WHERE city = 'Hà Nội'
GROUP BY product_name
ORDER BY total_revenue DESC
LIMIT 5;`
            : TOP_PRODUCTS_SQL,
          executionTimeMs: isHanoiProducts ? 137 : 124,
          rowCount: 5,
          status: "success",
        },
        visualization: {
          type: "bar",
          title: TOPIC_TITLES[topic],
          data: isHanoiProducts ? HANOI_TOP_PRODUCTS : TOP_PRODUCTS,
          unit: "tỷ VNĐ",
        },
        filters: isHanoiProducts ? filters : [],
      };

    case "city-revenue":
      return {
        topic,
        answer: answerOverride ?? "Hà Nội và TP.HCM đang đóng góp phần lớn doanh thu theo thành phố.",
        query: {
          sql: `SELECT
    city,
    SUM(revenue) AS total_revenue
FROM sales
GROUP BY city
ORDER BY total_revenue DESC;`,
          executionTimeMs: 103,
          rowCount: 5,
          status: "success",
        },
        visualization: {
          type: "bar",
          title: TOPIC_TITLES[topic],
          data: CITY_REVENUE,
          unit: "tỷ VNĐ",
        },
        filters,
      };
  }
}

function normalizeVietnamese(value: string): string {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/đ/g, "d")
    .replace(/Đ/g, "D")
    .toLocaleLowerCase("vi-VN");
}

function matchTopic(question: string): AnalysisTopic | undefined {
  const normalized = normalizeVietnamese(question);

  if (normalized.includes("top 5") || normalized.includes("san pham")) return "top-products";
  if (normalized.includes("theo thanh pho") || normalized.includes("thanh pho")) return "city-revenue";
  if (normalized.includes("xu huong") || normalized.includes("theo thang")) return "monthly-trend";
  if (normalized.includes("tong doanh thu") || normalized.includes("2026")) return "revenue-total";
  return undefined;
}

export async function askQuestion(
  question: string,
  context: ConversationContext = {},
): Promise<AnalysisResponse> {
  await new Promise<void>((resolve) => window.setTimeout(resolve, 620));

  const normalized = normalizeVietnamese(question);
  const asksForHanoi = normalized.includes("ha noi") || normalized.includes("hanoi");
  const current = context.currentAnalysis;

  if (asksForHanoi && current?.topic === "top-products") {
    return buildAnalysis("top-products", [HANOI_FILTER]);
  }

  const topic = matchTopic(question);
  if (topic) return buildAnalysis(topic);

  return {
    answer:
      "Mình đang dùng dữ liệu mô phỏng. Hãy thử hỏi về tổng doanh thu, xu hướng theo tháng, top sản phẩm hoặc doanh thu theo thành phố.",
    filters: [],
  };
}

export function updateAnalysisAfterFilterRemoval(
  analysis: AnalysisResponse,
  field: string,
): AnalysisResponse {
  if (!analysis.topic) return analysis;
  const filters = analysis.filters.filter((filter) => filter.field !== field);
  const removedFilter = analysis.filters.find((filter) => filter.field === field);
  const label = removedFilter?.label ?? removedFilter?.field ?? field;

  return buildAnalysis(
    analysis.topic,
    filters,
    removedFilter ? `Đã gỡ bộ lọc ${label} khỏi phân tích hiện tại.` : analysis.answer,
  );
}

export function loadDemoConversation(id: string): {
  conversation: DemoConversation;
  messages: ChatMessage[];
  analysis: AnalysisResponse;
} | null {
  const conversation = MOCK_CONVERSATIONS.find((item) => item.id === id);
  if (!conversation) return null;

  const timestamp = Date.now();
  let latestAnalysis: AnalysisResponse | undefined;
  const messages = conversation.turns.flatMap((turn, index): ChatMessage[] => {
    const result = buildAnalysis(turn.topic, turn.filters ?? []);
    latestAnalysis = result;
    const turnTime = timestamp - (conversation.turns.length - index) * 45_000;

    return [
      {
        id: `${conversation.id}-user-${index}`,
        role: "user",
        content: turn.question,
        createdAt: new Date(turnTime).toISOString(),
      },
      {
        id: `${conversation.id}-assistant-${index}`,
        role: "assistant",
        content: result.answer,
        createdAt: new Date(turnTime + 4_000).toISOString(),
        analysis: result,
      },
    ];
  });

  if (!latestAnalysis) return null;
  return { conversation, messages, analysis: latestAnalysis };
}

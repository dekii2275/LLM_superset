export type MessageRole = "user" | "assistant";

export type AnalysisTopic =
  | "revenue-total"
  | "monthly-trend"
  | "top-products"
  | "city-revenue";

export type AnalysisFilter = {
  field: string;
  operator: string;
  value: string | number;
  label?: string;
};

export type ChartDatum = {
  label: string;
  value: number;
};

export type VisualizationSpec =
  | {
      type: "big_number";
      title: string;
      value: number;
      formattedValue: string;
    }
  | {
      type: "line" | "bar";
      title: string;
      data: ChartDatum[];
      unit: string;
    };

export type QueryMetadata = {
  sql: string;
  executionTimeMs: number;
  rowCount: number;
  status: "success" | "error";
};

export type AnalysisResponse = {
  answer: string;
  topic?: AnalysisTopic;
  query?: QueryMetadata;
  visualization?: VisualizationSpec;
  filters: AnalysisFilter[];
};

export type ChatMessage = {
  id: string;
  role: MessageRole;
  content: string;
  createdAt: string;
  analysis?: AnalysisResponse;
};

export type DemoTurn = {
  question: string;
  topic: AnalysisTopic;
  filters?: AnalysisFilter[];
};

export type DemoConversation = {
  id: string;
  title: string;
  turns: DemoTurn[];
};

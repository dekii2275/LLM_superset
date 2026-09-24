import { Icon } from "@/components/ui/Icon";

const SUGGESTED_QUESTIONS = [
  "Tổng cộng có bao nhiêu chuyến taxi?",
  "Top 10 pickup zones có nhiều chuyến nhất?",
  "Tạo biểu đồ số chuyến theo tháng.",
  "Tạo dashboard tổng quan NYC Taxi.",
  "Thêm biểu đồ Trips by Day of Week vào dashboard hiện tại.",
  "Đổi Monthly Trip Volume thành bar chart.",
];

type SuggestedQuestionsProps = { onSelect: (question: string) => void };

export function SuggestedQuestions({ onSelect }: SuggestedQuestionsProps) {
  return (
    <div className="suggestion-grid" aria-label="Suggested questions">
      {SUGGESTED_QUESTIONS.map((question, index) => (
        <button className="suggestion-card" type="button" onClick={() => onSelect(question)} key={question}>
          <span className={`suggestion-icon suggestion-icon-${(index % 4) + 1}`}>
            <Icon name={index === 1 || index === 2 ? "chart" : index === 3 ? "database" : "sparkle"} size={16} />
          </span>
          <span>{question}</span>
          <Icon className="suggestion-arrow" name="arrow-up-right" size={15} />
        </button>
      ))}
    </div>
  );
}

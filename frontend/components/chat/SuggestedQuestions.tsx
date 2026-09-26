import { Icon } from "@/components/ui/Icon";

const SUGGESTED_QUESTIONS = [
  "Tổng cộng có bao nhiêu chuyến taxi?",
  "Top 10 khu vực đón khách có nhiều chuyến nhất?",
  "Tạo biểu đồ số chuyến theo tháng.",
  "Tạo bảng điều khiển tổng quan NYC Taxi.",
  "Thêm biểu đồ Số chuyến theo thứ trong tuần vào bảng điều khiển hiện tại.",
  "Đổi biểu đồ Lượng chuyến đi theo tháng thành biểu đồ cột.",
];

type SuggestedQuestionsProps = { onSelect: (question: string) => void; disabled: boolean };

export function SuggestedQuestions({ onSelect, disabled }: SuggestedQuestionsProps) {
  return (
    <div className="suggestion-grid" aria-label="Câu hỏi gợi ý">
      {SUGGESTED_QUESTIONS.map((question, index) => (
        <button className="suggestion-card" type="button" onClick={() => onSelect(question)} disabled={disabled} key={question}>
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

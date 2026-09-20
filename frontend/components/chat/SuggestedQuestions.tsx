import { SUGGESTED_QUESTIONS } from "@/lib/mock-data";
import { Icon } from "@/components/ui/Icon";

type SuggestedQuestionsProps = {
  onSelect: (question: string) => void;
};

export function SuggestedQuestions({ onSelect }: SuggestedQuestionsProps) {
  return (
    <div className="suggestion-grid" aria-label="Suggested questions">
      {SUGGESTED_QUESTIONS.map((question, index) => (
        <button className="suggestion-card" type="button" onClick={() => onSelect(question)} key={question}>
          <span className={`suggestion-icon suggestion-icon-${index + 1}`}>
            <Icon name={index === 2 ? "chart" : index === 3 ? "database" : "sparkle"} size={16} />
          </span>
          <span>{question}</span>
          <Icon className="suggestion-arrow" name="arrow-up-right" size={15} />
        </button>
      ))}
    </div>
  );
}

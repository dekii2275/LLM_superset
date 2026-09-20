import { Icon } from "@/components/ui/Icon";
import { SuggestedQuestions } from "./SuggestedQuestions";

type EmptyChatProps = {
  onAsk: (question: string) => void;
};

export function EmptyChat({ onAsk }: EmptyChatProps) {
  return (
    <div className="empty-chat">
      <div className="empty-chat-mark"><Icon name="sparkle" size={25} /></div>
      <p className="eyebrow">YOUR DATA, IN CONVERSATION</p>
      <h1>Ask your data<br /><span>anything.</span></h1>
      <p className="empty-chat-copy">
        Explore revenue, products, customers and trends using natural language.
      </p>
      <SuggestedQuestions onSelect={onAsk} />
      <div className="demo-note"><span className="status-dot demo" /> Demo mode · answers use sample analytics</div>
    </div>
  );
}

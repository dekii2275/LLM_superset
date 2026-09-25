import { Icon } from "@/components/ui/Icon";
import { SuggestedQuestions } from "./SuggestedQuestions";

type EmptyChatProps = {
  onAsk: (question: string) => void;
  disabled: boolean;
};

export function EmptyChat({ onAsk, disabled }: EmptyChatProps) {
  return (
    <div className="empty-chat">
      <div className="empty-chat-mark"><Icon name="sparkle" size={25} /></div>
      <p className="eyebrow">NYC YELLOW TAXI DATA</p>
      <h1>Ask your data<br /><span>anything.</span></h1>
      <p className="empty-chat-copy">
        Explore the connected Superset dataset using natural language.
      </p>
      <SuggestedQuestions onSelect={onAsk} disabled={disabled} />
    </div>
  );
}

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
      <p className="eyebrow">DỮ LIỆU TAXI VÀNG NYC</p>
      <h1>Hỏi dữ liệu của bạn<br /><span>bất cứ điều gì.</span></h1>
      <p className="empty-chat-copy">
        Khám phá tập dữ liệu Superset đã kết nối bằng ngôn ngữ tự nhiên.
      </p>
      <SuggestedQuestions onSelect={onAsk} disabled={disabled} />
    </div>
  );
}

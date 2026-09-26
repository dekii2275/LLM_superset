import { Icon } from "@/components/ui/Icon";

type ChatInputProps = {
  value: string;
  loading: boolean;
  llmEnabled: boolean | null;
  onChange: (value: string) => void;
  onSend: (question: string) => void;
};

export function ChatInput({ value, loading, llmEnabled, onChange, onSend }: ChatInputProps) {
  const canSend = value.trim().length > 0 && !loading && llmEnabled === true;
  const chatDisabled = llmEnabled !== true;

  return (
    <form
      className="chat-composer"
      onSubmit={(event) => {
        event.preventDefault();
        if (canSend) onSend(value);
      }}
    >
      <label className="sr-only" htmlFor="chat-question">Đặt câu hỏi về dữ liệu của bạn</label>
      <textarea
        id="chat-question"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            if (canSend) onSend(value);
          }
        }}
        placeholder={llmEnabled === false ? "Bật trò chuyện AI trong Cài đặt để đặt câu hỏi..." : llmEnabled === null ? "Đang tải cài đặt AI..." : "Đặt câu hỏi về dữ liệu của bạn..."}
        rows={1}
        disabled={loading || chatDisabled}
        aria-describedby="composer-hint"
      />
      <div className="composer-bottom">
        <span id="composer-hint" className="composer-hint">Shift + Enter để xuống dòng</span>
        <button className="send-button" type="submit" disabled={!canSend} aria-label="Gửi câu hỏi">
          {loading ? <span className="send-spinner" /> : <Icon name="arrow-up" size={17} />}
        </button>
      </div>
    </form>
  );
}

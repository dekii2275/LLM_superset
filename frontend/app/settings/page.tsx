"use client";

import { useEffect, useState } from "react";
import { AppLayout } from "@/components/layout/AppLayout";
import { getAISettings, setAIEnabled } from "@/lib/api";

export default function SettingsPage() {
  const [llmEnabled, setLlmEnabled] = useState<boolean | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let active = true;
    void getAISettings()
      .then((settings) => { if (active) setLlmEnabled(settings.llm_enabled); })
      .catch((requestError) => {
        if (active) setError(requestError instanceof Error ? requestError.message : "Không thể tải cài đặt AI.");
      });
    return () => { active = false; };
  }, []);

  const updateLlmSetting = async (enabled: boolean) => {
    setSaving(true);
    setError(null);
    try {
      const settings = await setAIEnabled(enabled);
      setLlmEnabled(settings.llm_enabled);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Không thể cập nhật cài đặt AI.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <AppLayout singleColumn>
      <section className="route-page">
        <header className="route-heading">
          <p className="panel-eyebrow">TÙY CHỈNH</p>
          <h1>Cài đặt</h1>
          <p>Kiểm soát việc trò chuyện AI có thể sử dụng khóa API trên máy chủ hay không.</p>
        </header>
        <section className="settings-card" aria-labelledby="ai-settings-title">
          <div className="settings-card-heading">
            <div className="settings-card-icon">AI</div>
            <div>
              <h2 id="ai-settings-title">Trò chuyện AI</h2>
              <p>Tắt tùy chọn này để ngăn câu hỏi được gửi đến mô hình ngôn ngữ.</p>
            </div>
          </div>
          <label className="ai-setting-row settings-toggle-row">
            <span>
              <b>Bật trò chuyện AI</b>
              <small>Khóa API luôn nằm trên máy chủ và không hiển thị tại đây.</small>
            </span>
            <input
              type="checkbox"
              checked={llmEnabled === true}
              disabled={llmEnabled === null || saving}
              onChange={(event) => { void updateLlmSetting(event.target.checked); }}
              aria-label="Bật trò chuyện AI"
            />
          </label>
          <p className="settings-status" role="status" aria-live="polite">
            {error ?? (saving ? "Đang lưu…" : llmEnabled === null ? "Đang tải cài đặt…" : llmEnabled ? "Đã bật trò chuyện AI" : "Đã tắt trò chuyện AI")}
          </p>
        </section>
      </section>
    </AppLayout>
  );
}

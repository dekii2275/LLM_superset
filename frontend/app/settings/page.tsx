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
        if (active) setError(requestError instanceof Error ? requestError.message : "Could not load AI settings.");
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
      setError(requestError instanceof Error ? requestError.message : "Could not update AI settings.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <AppLayout singleColumn>
      <section className="route-page">
        <header className="route-heading">
          <p className="panel-eyebrow">PREFERENCES</p>
          <h1>Settings</h1>
          <p>Control whether AI chat can use the server-side API key.</p>
        </header>
        <section className="settings-card" aria-labelledby="ai-settings-title">
          <div className="settings-card-heading">
            <div className="settings-card-icon">AI</div>
            <div>
              <h2 id="ai-settings-title">AI chat</h2>
              <p>Turn this off to prevent questions from being sent to the LLM.</p>
            </div>
          </div>
          <label className="ai-setting-row settings-toggle-row">
            <span>
              <b>Enable AI chat</b>
              <small>The API key stays on the server and is never shown here.</small>
            </span>
            <input
              type="checkbox"
              checked={llmEnabled === true}
              disabled={llmEnabled === null || saving}
              onChange={(event) => { void updateLlmSetting(event.target.checked); }}
              aria-label="Enable AI chat"
            />
          </label>
          <p className="settings-status" role="status" aria-live="polite">
            {error ?? (saving ? "Saving…" : llmEnabled === null ? "Loading settings…" : llmEnabled ? "AI chat is on" : "AI chat is off")}
          </p>
        </section>
      </section>
    </AppLayout>
  );
}

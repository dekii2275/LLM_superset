"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { AppHeader } from "@/components/layout/AppHeader";
import { Sidebar } from "@/components/layout/Sidebar";
import { ChatPanel } from "@/components/chat/ChatPanel";
import { SqlViewer } from "@/components/sql/SqlViewer";
import { VisualizationPanel } from "@/components/visualization/VisualizationPanel";
import { askQuestion, loadDemoConversation, updateAnalysisAfterFilterRemoval } from "@/lib/mock-api";
import type { AnalysisResponse, ChatMessage } from "@/lib/types";

export default function Home() {
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);
  const [conversationTitle, setConversationTitle] = useState("New Analysis");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [analysis, setAnalysis] = useState<AnalysisResponse | null>(null);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sqlAnalysis, setSqlAnalysis] = useState<AnalysisResponse | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const loadingRef = useRef(false);
  const requestIdRef = useRef(0);

  const handleNewAnalysis = useCallback(() => {
    requestIdRef.current += 1;
    setActiveConversationId(null);
    setConversationTitle("New Analysis");
    setMessages([]);
    setAnalysis(null);
    setInput("");
    setError(null);
    setSqlAnalysis(null);
    loadingRef.current = false;
    setLoading(false);
    setSidebarOpen(false);
  }, []);

  useEffect(() => {
    const handleShortcut = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        handleNewAnalysis();
      }
    };
    window.addEventListener("keydown", handleShortcut);
    return () => window.removeEventListener("keydown", handleShortcut);
  }, [handleNewAnalysis]);

  const handleSelectConversation = (id: string) => {
    const loaded = loadDemoConversation(id);
    if (!loaded) return;
    requestIdRef.current += 1;
    setActiveConversationId(loaded.conversation.id);
    setConversationTitle(loaded.conversation.title);
    setMessages(loaded.messages);
    setAnalysis(loaded.analysis);
    setInput("");
    setError(null);
    setSqlAnalysis(null);
    setLoading(false);
    loadingRef.current = false;
    setSidebarOpen(false);
  };

  const handleSend = async (question: string) => {
    const trimmed = question.trim();
    if (!trimmed || loadingRef.current) return;

    const requestId = ++requestIdRef.current;
    loadingRef.current = true;
    setLoading(true);
    setInput("");
    setError(null);
    setActiveConversationId((current) => current ?? "current-session");
    setConversationTitle((current) => current === "New Analysis" ? trimmed.slice(0, 34) : current);

    const userMessage: ChatMessage = {
      id: `user-${Date.now()}`,
      role: "user",
      content: trimmed,
      createdAt: new Date().toISOString(),
    };
    setMessages((current) => [...current, userMessage]);

    try {
      const response = await askQuestion(trimmed, { currentAnalysis: analysis ?? undefined });
      if (requestId !== requestIdRef.current) return;
      const assistantMessage: ChatMessage = {
        id: `assistant-${Date.now()}`,
        role: "assistant",
        content: response.answer,
        createdAt: new Date().toISOString(),
        analysis: response,
      };
      setMessages((current) => [...current, assistantMessage]);
      setAnalysis(response);
    } catch {
      if (requestId === requestIdRef.current) {
        setError("Something went wrong while preparing the demo response. Please try again.");
      }
    } finally {
      if (requestId === requestIdRef.current) {
        loadingRef.current = false;
        setLoading(false);
      }
    }
  };

  const handleViewSql = useCallback((selected: AnalysisResponse) => {
    setSqlAnalysis(selected);
  }, []);

  const handleCloseSql = useCallback(() => {
    setSqlAnalysis(null);
  }, []);

  const handleViewVisualization = (selected: AnalysisResponse) => {
    setAnalysis(selected);
    document.querySelector(".visualization-panel")?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  };

  const handleRemoveFilter = (field: string) => {
    if (!analysis) return;
    const updated = updateAnalysisAfterFilterRemoval(analysis, field);
    setAnalysis(updated);
    setMessages((current) => {
      let lastAnalysisMessage = -1;
      for (let index = current.length - 1; index >= 0; index -= 1) {
        if (current[index].role === "assistant" && current[index].analysis) {
          lastAnalysisMessage = index;
          break;
        }
      }
      if (lastAnalysisMessage < 0) return current;
      return current.map((message, index) => index === lastAnalysisMessage
        ? { ...message, content: updated.answer, analysis: updated }
        : message);
    });
  };

  return (
    <div className={`app-frame ${sidebarOpen ? "sidebar-open" : ""}`}>
      <AppHeader sidebarOpen={sidebarOpen} onToggleSidebar={() => setSidebarOpen((open) => !open)} />
      <main className="workspace" id="main">
        <Sidebar
          activeConversationId={activeConversationId}
          onNewAnalysis={handleNewAnalysis}
          onSelectConversation={handleSelectConversation}
        />
        {sidebarOpen && (
          <button
            className="mobile-sidebar-scrim"
            type="button"
            aria-label="Close navigation"
            onClick={() => setSidebarOpen(false)}
          />
        )}
        <ChatPanel
          title={conversationTitle}
          messages={messages}
          input={input}
          loading={loading}
          error={error}
          onInputChange={setInput}
          onSend={handleSend}
          onViewSql={handleViewSql}
          onViewVisualization={handleViewVisualization}
        />
        <VisualizationPanel analysis={analysis} onRemoveFilter={handleRemoveFilter} />
      </main>
      <SqlViewer analysis={sqlAnalysis} onClose={handleCloseSql} />
    </div>
  );
}

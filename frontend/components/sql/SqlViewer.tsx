"use client";

import { useEffect, useRef, useState } from "react";
import type { AnalysisResponse } from "@/lib/types";
import { Icon } from "@/components/ui/Icon";

type SqlViewerProps = {
  analysis: AnalysisResponse | null;
  onClose: () => void;
};

export function SqlViewer({ analysis, onClose }: SqlViewerProps) {
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const [copyState, setCopyState] = useState<"idle" | "copied" | "error">("idle");
  const query = analysis?.query;

  useEffect(() => {
    if (!query) return;
    closeButtonRef.current?.focus();
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose, query]);

  useEffect(() => setCopyState("idle"), [query?.sql]);

  if (!query) return null;

  const copySql = async () => {
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(query.sql);
      } else {
        const textarea = document.createElement("textarea");
        textarea.value = query.sql;
        textarea.setAttribute("readonly", "");
        textarea.style.position = "fixed";
        textarea.style.opacity = "0";
        document.body.appendChild(textarea);
        textarea.select();
        const copied = document.execCommand("copy");
        textarea.remove();
        if (!copied) throw new Error("Clipboard is unavailable");
      }
      setCopyState("copied");
    } catch {
      setCopyState("error");
    }
  };

  return (
    <div className="sql-overlay" role="presentation" onMouseDown={(event) => {
      if (event.target === event.currentTarget) onClose();
    }}>
      <section className="sql-dialog" role="dialog" aria-modal="true" aria-labelledby="sql-title">
        <div className="sql-dialog-header">
          <div>
            <p className="panel-eyebrow">QUERY DETAILS</p>
            <h2 id="sql-title">Generated SQL</h2>
          </div>
          <button className="icon-button" type="button" onClick={onClose} aria-label="Close SQL viewer" ref={closeButtonRef}>
            <Icon name="close" />
          </button>
        </div>

        <div className="sql-code-heading">
          <span><i className="code-language-dot" /> SQL · PostgreSQL</span>
          <button className="copy-sql-button" type="button" onClick={() => void copySql()}>
            <Icon name={copyState === "copied" ? "check" : "copy"} size={14} />
            {copyState === "copied" ? "Copied" : "Copy SQL"}
          </button>
        </div>
        <pre className="sql-code"><code>{query.sql}</code></pre>
        <div className="sql-query-status">
          <div className="sql-status-title"><span className={`status-dot ${query.status === "success" ? "connected" : "disconnected"}`} />
            Query status: {query.status === "success" ? "Success" : "Error"}
          </div>
          <div className="sql-meta-grid">
            <span>Execution time<strong>{query.executionTimeMs} ms</strong></span>
            <span>Rows returned<strong>{query.rowCount}</strong></span>
          </div>
          <p className={`copy-feedback ${copyState}`} role="status" aria-live="polite">
            {copyState === "copied" ? "SQL copied to clipboard." : copyState === "error" ? "Clipboard access is unavailable." : ""}
          </p>
        </div>
        <p className="sql-demo-note">Demo query only · it has not been executed against a database.</p>
      </section>
    </div>
  );
}

"use client";

import { useEffect, useState } from "react";
import { StatusCard } from "@/components/StatusCard";
import { apiUrl, checkEndpoint } from "@/lib/api";

type Status = "Checking" | "Connected" | "Disconnected";

export default function Home() {
  const [backend, setBackend] = useState<Status>("Checking");
  const [database, setDatabase] = useState<Status>("Checking");
  const [superset, setSuperset] = useState<Status>("Checking");

  useEffect(() => {
    let active = true;

    const refresh = async () => {
      const [backendIsUp, databaseIsUp, supersetIsUp] = await Promise.all([
        checkEndpoint(apiUrl("/health")),
        checkEndpoint(apiUrl("/health/db")),
        checkEndpoint(apiUrl("/health/superset")),
      ]);

      if (active) {
        setBackend(backendIsUp ? "Connected" : "Disconnected");
        setDatabase(databaseIsUp ? "Connected" : "Disconnected");
        setSuperset(supersetIsUp ? "Connected" : "Disconnected");
      }
    };

    void refresh();
    const timer = window.setInterval(() => void refresh(), 30000);

    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, []);

  return (
    <main className="page-shell">
      <section className="hero">
        <p className="eyebrow">Analytics workspace</p>
        <h1>AI BI Assistant</h1>
        <p className="subtitle">Natural Language Analytics powered by Superset</p>
      </section>

      <section className="status-section" aria-labelledby="status-heading">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Infrastructure</p>
            <h2 id="status-heading">Service status</h2>
          </div>
          <span className="refresh-note">Refreshes every 30 seconds</span>
        </div>

        <div className="status-grid">
          <StatusCard name="Frontend" status="Connected" detail="Next.js · port 43117" />
          <StatusCard name="Backend" status={backend} detail="FastAPI · port 48123" />
          <StatusCard name="Database" status={database} detail="PostgreSQL · port 55439" />
          <StatusCard
            name="Superset"
            status={superset}
            detail="Apache Superset · port 58088"
            href={process.env.NEXT_PUBLIC_SUPERSET_URL}
          />
        </div>
      </section>

      <footer className="footer">Infrastructure skeleton · no business dataset loaded</footer>
    </main>
  );
}

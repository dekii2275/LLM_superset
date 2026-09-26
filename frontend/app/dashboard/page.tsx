"use client";

import { useRouter } from "next/navigation";
import { AppLayout } from "@/components/layout/AppLayout";
import { EmbeddedDashboard } from "@/components/superset/EmbeddedDashboard";

export default function DashboardPage() {
  const router = useRouter();

  return (
    <AppLayout singleColumn>
      <section className="route-page dashboard-route" aria-label="Bảng điều khiển NYC Taxi">
        <EmbeddedDashboard onClose={() => router.push("/")} />
      </section>
    </AppLayout>
  );
}

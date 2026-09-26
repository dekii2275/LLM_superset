import Image from "next/image";
import Link from "next/link";
import { Icon } from "@/components/ui/Icon";
import { ServiceStatus } from "@/components/system/ServiceStatus";

type AppHeaderProps = {
  sidebarOpen: boolean;
  onToggleSidebar: () => void;
};

export function AppHeader({ sidebarOpen, onToggleSidebar }: AppHeaderProps) {
  return (
    <header className="app-header">
      <button
        className="icon-button menu-toggle"
        type="button"
        onClick={onToggleSidebar}
        aria-label={sidebarOpen ? "Đóng điều hướng" : "Mở điều hướng"}
        aria-expanded={sidebarOpen}
        aria-controls="app-sidebar"
      >
        <Icon name="menu" />
      </button>

      <Link className="brand" href="/" aria-label="Trang chủ AI BI Assistant">
        <Image
          className="brand-logo"
          src="/branding/ai-bi-logo.png"
          alt="AI BI — Artificial Intelligence + Business Intelligence"
          width={2129}
          height={739}
          preload
        />
        <span className="brand-copy">
          <strong>AI BI Assistant</strong>
          <small>Phân tích hội thoại trên nền tảng Superset</small>
        </span>
      </Link>

      <div className="header-actions">
        <Link className="settings-button" href="/settings">Cài đặt</Link>
        <ServiceStatus />
      </div>
    </header>
  );
}

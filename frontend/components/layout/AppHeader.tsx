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
        aria-label={sidebarOpen ? "Close navigation" : "Open navigation"}
        aria-expanded={sidebarOpen}
        aria-controls="app-sidebar"
      >
        <Icon name="menu" />
      </button>

      <Link className="brand" href="/" aria-label="AI BI Assistant home">
        <span className="brand-mark"><Icon name="sparkle" size={19} /></span>
        <span className="brand-copy">
          <strong>AI BI Assistant</strong>
          <small>Conversational Analytics powered by Superset</small>
        </span>
      </Link>

      <div className="header-actions">
        <Link className="settings-button" href="/settings">Settings</Link>
        <ServiceStatus />
      </div>
    </header>
  );
}

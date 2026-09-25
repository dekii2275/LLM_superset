"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Icon } from "@/components/ui/Icon";

type SidebarProps = {
  onNewAnalysis?: () => void;
};

const navigation = [
  { href: "/", label: "Home", icon: "sparkle" as const },
  { href: "/dashboard", label: "Dashboard", icon: "chart" as const },
  { href: "/profile", label: "Profile", icon: "user" as const },
  { href: "/settings", label: "Settings", icon: "settings" as const },
];

export function Sidebar({ onNewAnalysis }: SidebarProps) {
  const pathname = usePathname();

  return (
    <aside className="sidebar" id="app-sidebar" aria-label="Workspace navigation">
      <div className="sidebar-topline">
        <span className="workspace-label">WORKSPACE</span>
        <span className="workspace-switcher" aria-label="Personal workspace">P</span>
      </div>

      {onNewAnalysis ? (
        <button className="new-analysis-button" type="button" onClick={onNewAnalysis}>
          <Icon name="plus" size={17} />
          <span>New Analysis</span>
          <kbd>⌘ K</kbd>
        </button>
      ) : (
        <Link className="new-analysis-button" href="/">
          <Icon name="plus" size={17} />
          <span>New Analysis</span>
          <kbd>⌘ K</kbd>
        </Link>
      )}

      <div className="sidebar-section-heading">
        <span>PAGES</span>
      </div>

      <nav className="conversation-nav" aria-label="Pages">
        {navigation.map(({ href, label, icon }) => {
          const active = pathname === href;
          return (
            <Link key={href} className={`conversation-link ${active ? "active" : ""}`} href={href} aria-current={active ? "page" : undefined}>
              <Icon name={icon} size={15} />
              <span>{label}</span>
            </Link>
          );
        })}
      </nav>

      <div className="sidebar-bottom">
        <div className="source-heading">
          <span className="source-icon"><Icon name="database" size={16} /></span>
          <div>
            <span className="source-kicker">DATA SOURCE</span>
            <strong>NYC Yellow Taxi</strong>
          </div>
          <span className="source-menu" aria-hidden="true">•••</span>
        </div>
        <div className="source-status">
          <span className="status-dot connected" />
          <span>Connected</span>
        </div>
        <Link className="sidebar-profile" href="/profile" aria-label="View Analytics Team profile">
          <span className="profile-avatar">AN</span>
          <div>
            <strong>Analytics Team</strong>
            <span>Analytics workspace</span>
          </div>
          <span className="profile-menu" aria-hidden="true">•••</span>
        </Link>
      </div>
    </aside>
  );
}

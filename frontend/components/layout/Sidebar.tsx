"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Icon } from "@/components/ui/Icon";

type SidebarProps = {
  onNewAnalysis?: () => void;
};

const navigation = [
  { href: "/", label: "Trang chủ", icon: "sparkle" as const },
  { href: "/dashboard", label: "Bảng điều khiển", icon: "chart" as const },
  { href: "/profile", label: "Hồ sơ", icon: "user" as const },
  { href: "/settings", label: "Cài đặt", icon: "settings" as const },
];

export function Sidebar({ onNewAnalysis }: SidebarProps) {
  const pathname = usePathname();

  return (
    <aside className="sidebar" id="app-sidebar" aria-label="Điều hướng không gian làm việc">
      <div className="sidebar-topline">
        <span className="workspace-label">KHÔNG GIAN LÀM VIỆC</span>
        <span className="workspace-switcher" aria-label="Không gian làm việc cá nhân">P</span>
      </div>

      {onNewAnalysis ? (
        <button className="new-analysis-button" type="button" onClick={onNewAnalysis}>
          <Icon name="plus" size={17} />
          <span>Phân tích mới</span>
          <kbd>⌘ K</kbd>
        </button>
      ) : (
        <Link className="new-analysis-button" href="/">
          <Icon name="plus" size={17} />
          <span>Phân tích mới</span>
          <kbd>⌘ K</kbd>
        </Link>
      )}

      <div className="sidebar-section-heading">
        <span>TRANG</span>
      </div>

      <nav className="conversation-nav" aria-label="Các trang">
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
            <span className="source-kicker">NGUỒN DỮ LIỆU</span>
            <strong>Taxi Vàng NYC</strong>
          </div>
          <span className="source-menu" aria-hidden="true">•••</span>
        </div>
        <div className="source-status">
          <span className="status-dot connected" />
          <span>Đã kết nối</span>
        </div>
        <Link className="sidebar-profile" href="/profile" aria-label="Xem hồ sơ Nhóm Phân tích">
          <span className="profile-avatar">AN</span>
          <div>
            <strong>Nhóm Phân tích</strong>
            <span>Không gian làm việc phân tích</span>
          </div>
          <span className="profile-menu" aria-hidden="true">•••</span>
        </Link>
      </div>
    </aside>
  );
}

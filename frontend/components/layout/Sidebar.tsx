"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Icon } from "@/components/ui/Icon";

import type { ChatSession } from "@/lib/types";

type SidebarProps = {
  onNewAnalysis?: () => void;
  sessions?: ChatSession[];
  activeSessionId?: string | null;
  onSelectSession?: (id: string) => void;
  onDeleteSession?: (id: string) => void;
};

const navigation = [
  { href: "/", label: "Trang chủ", icon: "sparkle" as const },
  { href: "/dashboard", label: "Bảng điều khiển", icon: "chart" as const },
  { href: "/datasets", label: "Quản lý dữ liệu", icon: "database" as const },
  { href: "/settings", label: "Cài đặt", icon: "settings" as const },
];

export function Sidebar({
  onNewAnalysis,
  sessions,
  activeSessionId,
  onSelectSession,
  onDeleteSession,
}: SidebarProps) {
  const pathname = usePathname();

  return (
    <aside className="sidebar" id="app-sidebar" aria-label="Điều hướng không gian làm việc">
      <div className="sidebar-topline">
        <span className="workspace-label">KHÔNG GIAN LÀM VIỆC</span>
        <span className="workspace-switcher" aria-label="Không gian làm việc cá nhân">
          P
        </span>
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
            <Link
              key={href}
              className={`conversation-link ${active ? "active" : ""}`}
              href={href}
              aria-current={active ? "page" : undefined}
            >
              <Icon name={icon} size={15} />
              <span>{label}</span>
            </Link>
          );
        })}
      </nav>

      {sessions && sessions.length > 0 && (
        <>
          <div className="sidebar-section-heading session-history-heading">
            <span>LỊCH SỬ HỘI THOẠI</span>
            <span className="session-count-badge">{sessions.length}</span>
          </div>
          <div className="sidebar-sessions-list" aria-label="Danh sách phiên hội thoại">
            {sessions.map((s) => {
              const isSelected = activeSessionId === s.id;
              return (
                <div key={s.id} className={`sidebar-session-item ${isSelected ? "active" : ""}`}>
                  <button
                    type="button"
                    className="sidebar-session-btn"
                    onClick={() => onSelectSession?.(s.id)}
                    title={s.title}
                  >
                    <Icon name="message" size={13} />
                    <span className="session-title-text">{s.title}</span>
                  </button>
                  {onDeleteSession && (
                    <button
                      type="button"
                      className="session-delete-btn"
                      onClick={(e) => {
                        e.stopPropagation();
                        onDeleteSession(s.id);
                      }}
                      title="Xóa phiên này"
                    >
                      <Icon name="trash" size={12} />
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        </>
      )}

      <div className="sidebar-bottom">
        <div className="sidebar-profile" aria-label="Nhóm Phân tích">
          <span className="profile-avatar">AN</span>
          <div>
            <strong>Nhóm Phân tích</strong>
            <span>Không gian làm việc phân tích</span>
          </div>
        </div>
      </div>
    </aside>
  );
}

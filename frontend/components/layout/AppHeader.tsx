import Image from "next/image";
import Link from "next/link";
import { Icon } from "@/components/ui/Icon";

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
        <Image className="brand-logo" src="/superset-logo-transparent.png" alt="Apache Superset" width={110} height={64} loading="eager" />
      </Link>
    </header>
  );
}

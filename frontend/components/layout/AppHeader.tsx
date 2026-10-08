import Image from "next/image";
import Link from "next/link";
import { Icon } from "@/components/ui/Icon";
import type { DatasetSummary } from "@/lib/types";

import { DatasetSelector } from "./DatasetSelector";
import { UserMenu } from "@/components/auth/UserMenu";
import { LoginModal } from "@/components/auth/LoginModal";
import { AlertsDropdown } from "@/components/alerts/AlertsDropdown";

type AppHeaderProps = {
  sidebarOpen: boolean;
  onToggleSidebar: () => void;
  activeDatasetId?: number | null;
  onSelectDataset?: (id: number, dataset?: DatasetSummary) => void;
};

export function AppHeader({
  sidebarOpen,
  onToggleSidebar,
  activeDatasetId,
  onSelectDataset,
}: AppHeaderProps) {
  return (
    <>
      <header className="app-header">
        <div className="app-header-left">
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
              src="/superset-logo-transparent.png"
              alt="Apache Superset"
              width={110}
              height={64}
              loading="eager"
            />
          </Link>
        </div>

        <div className="app-header-right">
          <DatasetSelector activeDatasetId={activeDatasetId} onSelectDataset={onSelectDataset} />
          <AlertsDropdown activeDatasetId={activeDatasetId} />
          <UserMenu activeDatasetId={activeDatasetId} />
        </div>
      </header>
      <LoginModal />
    </>
  );
}

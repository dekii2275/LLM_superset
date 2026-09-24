import { Icon } from "@/components/ui/Icon";

type SidebarProps = {
  onNewAnalysis: () => void;
};

export function Sidebar({ onNewAnalysis }: SidebarProps) {
  return (
    <aside className="sidebar" id="app-sidebar" aria-label="Workspace navigation">
      <div className="sidebar-topline">
        <span className="workspace-label">WORKSPACE</span>
        <span className="workspace-switcher" aria-label="Personal workspace">P</span>
      </div>

      <button className="new-analysis-button" type="button" onClick={onNewAnalysis}>
        <Icon name="plus" size={17} />
        <span>New Analysis</span>
        <kbd>⌘ K</kbd>
      </button>

      <div className="sidebar-section-heading">
        <span>RECENT</span>
        <button className="subtle-icon-button" type="button" aria-label="Recent analyses">
          <span aria-hidden="true">•••</span>
        </button>
      </div>

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
        <div className="sidebar-profile">
          <span className="profile-avatar">AN</span>
          <div>
            <strong>Analytics Team</strong>
            <span>Analytics workspace</span>
          </div>
          <span className="profile-menu" aria-hidden="true">•••</span>
        </div>
      </div>
    </aside>
  );
}

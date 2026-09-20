import { MOCK_CONVERSATIONS } from "@/lib/mock-data";
import { Icon } from "@/components/ui/Icon";

type SidebarProps = {
  activeConversationId: string | null;
  onNewAnalysis: () => void;
  onSelectConversation: (id: string) => void;
};

export function Sidebar({ activeConversationId, onNewAnalysis, onSelectConversation }: SidebarProps) {
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

      <nav className="conversation-nav" aria-label="Recent analyses">
        {MOCK_CONVERSATIONS.map((conversation, index) => (
          <button
            className={`conversation-link ${activeConversationId === conversation.id ? "active" : ""}`}
            key={conversation.id}
            type="button"
            onClick={() => onSelectConversation(conversation.id)}
            aria-current={activeConversationId === conversation.id ? "page" : undefined}
          >
            <Icon name={index === 3 ? "message" : "chart"} size={16} />
            <span>{conversation.title}</span>
          </button>
        ))}
      </nav>

      <div className="sidebar-bottom">
        <div className="source-heading">
          <span className="source-icon"><Icon name="database" size={16} /></span>
          <div>
            <span className="source-kicker">DATA SOURCE</span>
            <strong>E-commerce Analytics</strong>
          </div>
          <span className="source-menu" aria-hidden="true">•••</span>
        </div>
        <div className="source-status">
          <span className="status-dot demo" />
          <span>Connected</span>
          <span className="mock-source-label">Mock</span>
        </div>
        <div className="sidebar-profile">
          <span className="profile-avatar">AN</span>
          <div>
            <strong>Analytics Team</strong>
            <span>Demo workspace</span>
          </div>
          <span className="profile-menu" aria-hidden="true">•••</span>
        </div>
      </div>
    </aside>
  );
}
